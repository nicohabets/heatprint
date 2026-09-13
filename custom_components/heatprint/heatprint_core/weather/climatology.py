"""Climatology: mean TAC, wind and degree days per day of year (METHODS section 8.1).

Days of year are indexed in a leap-year calendar (``leap_doy``: Jan 1 = 1, Feb 28 = 59,
Feb 29 = 60, Mar 1 = 61, Dec 31 = 366) so that every calendar date maps to the same
slot in every year. Slot 60 (Feb 29) pools the Feb 29 samples of leap years with the
Feb 28 and Mar 1 samples of all years so that it is never empty or noisy.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta

from ..flags import Flag
from ..methods.degree_days import compute_day
from ..models import Climatology, DailyRecord, DailyWeather, MethodConfig

_LOGGER = logging.getLogger(__name__)

TacFn = Callable[[DailyWeather, DailyWeather | None], float]
DdFn = Callable[[DailyWeather, DailyWeather | None], float]

DOY_SLOTS = 366
FEB29_SLOT = 60


def leap_doy(day: date) -> int:
    """Day of year in a leap-year calendar (1..366); Mar 1 is always 61."""
    doy = day.timetuple().tm_yday
    if not _is_leap(day.year) and (day.month > 2):
        doy += 1
    return doy


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


class _Accumulator:
    def __init__(self) -> None:
        self.sums: list[float] = [0.0] * DOY_SLOTS
        self.counts: list[int] = [0] * DOY_SLOTS

    def add(self, slot: int, value: float | None) -> None:
        if value is None:
            return
        self.sums[slot - 1] += value
        self.counts[slot - 1] += 1

    def means(self) -> list[float | None]:
        return [
            (self.sums[i] / self.counts[i]) if self.counts[i] else None for i in range(DOY_SLOTS)
        ]


def build_climatology(
    records_or_weather: Iterable[DailyRecord | DailyWeather],
    years: int = 20,
    tac_fn: TacFn | None = None,
    dd_fns: Mapping[str, DdFn] | None = None,
    *,
    site_id: str = "",
    end: date | None = None,
    computed_at: date | None = None,
    method_config: MethodConfig | None = None,
    house_balance_temp: float | None = None,
    tac_preset: str = "house",
) -> Climatology:
    """Build the climatology from daily records or raw daily weather.

    - :class:`DailyRecord` input: uses ``tac_house`` (or ``tac_pbl`` when
      ``tac_preset="pbl"``), ``wind_mean`` and the stored ``dd`` values; days flagged
      ``WEATHER_MISSING`` are skipped.
    - :class:`DailyWeather` input: ``tac_fn(today, yesterday)`` and each
      ``dd_fns[name](today, yesterday)`` compute the values; when both are None the
      degree-day methods of ``method_config`` (default config) are used via
      :func:`compute_day`, with ``tac_house`` as TAC.

    Only the last ``years`` years before ``end`` (default: the last date in the data)
    are used.
    """
    items = sorted(records_or_weather, key=lambda item: item.date)
    if not items:
        raise ValueError("no data for climatology")
    last = end or items[-1].date
    cutoff = last - timedelta(days=round(365.25 * years))
    tac_acc, wind_acc = _Accumulator(), _Accumulator()
    dd_accs: dict[str, _Accumulator] = {}

    by_date: dict[date, DailyWeather] = {
        item.date: item for item in items if isinstance(item, DailyWeather)
    }
    used = 0
    for item in items:
        if not (cutoff < item.date <= last):
            continue
        if isinstance(item, DailyRecord):
            if Flag.WEATHER_MISSING in item.flags:
                continue
            tac = item.tac_pbl if tac_preset == "pbl" else item.tac_house
            wind = item.wind_mean
            dd_values: dict[str, float] = dict(item.dd)
        else:
            yesterday = by_date.get(item.date - timedelta(days=1))
            if tac_fn is None and dd_fns is None:
                day_methods = compute_day(item, yesterday, method_config, house_balance_temp)
                tac = day_methods.tac_pbl if tac_preset == "pbl" else day_methods.tac_house
                dd_values = day_methods.dd
            else:
                tac = tac_fn(item, yesterday) if tac_fn is not None else None
                dd_values = {name: fn(item, yesterday) for name, fn in (dd_fns or {}).items()}
            wind = item.wind_mean
        if tac is None:
            continue
        used += 1
        for slot in _slots_for(item.date):
            tac_acc.add(slot, tac)
            wind_acc.add(slot, wind)
            for name, value in dd_values.items():
                dd_accs.setdefault(name, _Accumulator()).add(slot, value)

    _LOGGER.debug("climatology built from %d days (%d years window)", used, years)
    samples = [tac_acc.counts[i] for i in range(DOY_SLOTS)]
    return Climatology(
        site_id=site_id,
        years=years,
        tac_by_doy=tac_acc.means(),
        wind_by_doy=wind_acc.means(),
        dd_by_doy={name: acc.means() for name, acc in dd_accs.items()},
        computed_at=computed_at or date.today(),
        tac_preset=tac_preset,
        samples_by_doy=samples,
    )


def _slots_for(day: date) -> tuple[int, ...]:
    """Slots that a date contributes to: its own, plus slot 60 for Feb 28 and Mar 1."""
    slot = leap_doy(day)
    if (day.month, day.day) in ((2, 28), (3, 1)):
        return (slot, FEB29_SLOT)
    return (slot,)


def climatology_value(clim: Climatology, kind: str, day: date) -> float | None:
    """Value for ``day``: ``kind`` is ``"tac"``, ``"wind"`` or a degree-day method name."""
    index = leap_doy(day) - 1
    if kind == "tac":
        return clim.tac_by_doy[index] if index < len(clim.tac_by_doy) else None
    if kind == "wind":
        return clim.wind_by_doy[index] if index < len(clim.wind_by_doy) else None
    series = clim.dd_by_doy.get(kind)
    if series is None or index >= len(series):
        return None
    return series[index]


def season_dd_clim(
    clim: Climatology, method: str, start: date, end: date, balance_temp: float | None = None
) -> float:
    """Sum of climatological degree days of ``method`` over ``start``..``end`` inclusive.

    For ``method="house"`` with a ``balance_temp`` and no stored house series the value
    is derived from the TAC climatology as ``max(0, T_b - TAC_clim)``.
    """
    total = 0.0
    day = start
    derive_house = method == "house" and balance_temp is not None and "house" not in clim.dd_by_doy
    while day <= end:
        if derive_house:
            tac = climatology_value(clim, "tac", day)
            value = None if tac is None else max(0.0, balance_temp - tac)
        else:
            value = climatology_value(clim, method, day)
        if value is not None:
            total += value
        day += timedelta(days=1)
    return total


def remaining_season_dd(
    clim: Climatology,
    method: str,
    from_date: date,
    season_end: date,
    balance_temp: float | None = None,
) -> float:
    """Climatological degree days from ``from_date`` to ``season_end`` (METHODS section 8.5)."""
    if from_date > season_end:
        return 0.0
    return season_dd_clim(clim, method, from_date, season_end, balance_temp)
