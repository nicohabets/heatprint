"""Period comparison, mindergas style, and measure effects (METHODS sections 8.3-8.4).

::

    k_i     = Q_space(period_i) / sum dd[method](period_i)
    delta % = (k_2 - k_1) / k_1 * 100

Both periods need at least ``min_days`` usable days and a degree-day sum of at least
100 (classic) or 50 (other methods).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta

from ..flags import is_usable
from ..models import Climatology, Comparison, DailyRecord, Period, SeasonConfig, SignatureFit
from ..season import season_for
from .normalize import normalized_consumption, saving_between
from .signature import fit_signature

_LOGGER = logging.getLogger(__name__)

MIN_DD_BY_METHOD: dict[str, float] = {"classic": 100.0}
DEFAULT_MIN_DD = 50.0


class InsufficientDataError(ValueError):
    """Raised when a period does not meet the minimum requirements of a comparison."""


@dataclass(frozen=True)
class PeriodStats:
    """Usable days, heat and degree days of one period."""

    period: Period
    n_days: int
    heat_space_kwh: float
    degree_days: float

    @property
    def k(self) -> float:
        """Heat per degree day (kWh/K)."""
        return self.heat_space_kwh / self.degree_days if self.degree_days > 0 else float("nan")


def period_stats(records: Iterable[DailyRecord], period: Period, method: str) -> PeriodStats:
    """Sum heat and degree days over the usable days of ``period``."""
    n = 0
    heat = 0.0
    dd = 0.0
    for record in records:
        if not period.contains(record.date) or not is_usable(record.flags):
            continue
        value = record.dd.get(method)
        if value is None:
            continue
        n += 1
        heat += record.heat_space_kwh
        dd += value
    return PeriodStats(period, n, heat, dd)


def min_degree_days(method: str) -> float:
    """Minimum degree-day sum for a comparison with ``method``."""
    return MIN_DD_BY_METHOD.get(method, DEFAULT_MIN_DD)


def _check(stats: PeriodStats, method: str, min_days: int, min_dd: float | None, name: str) -> None:
    threshold = min_degree_days(method) if min_dd is None else min_dd
    if stats.n_days < min_days:
        raise InsufficientDataError(
            f"{name} period has {stats.n_days} usable days, at least {min_days} required"
        )
    # k = Q / Σdd is undefined when there are no degree days, even if the caller
    # lowered ``min_dd`` to 0 (METHODS section 8.3). Never return NaN.
    if stats.degree_days <= 0:
        raise InsufficientDataError(
            f"{name} period has no degree days ({method}); cannot compute k"
        )
    if stats.degree_days < threshold:
        raise InsufficientDataError(
            f"{name} period has {stats.degree_days:.1f} degree days ({method}), "
            f"at least {threshold:.0f} required"
        )


def compare_periods(
    records: Iterable[DailyRecord],
    base: Period,
    target: Period,
    method: str = "classic",
    min_days: int = 30,
    min_dd: float | None = None,
) -> Comparison:
    """Compare heat per degree day of two periods (METHODS section 8.3).

    Raises :class:`InsufficientDataError` when a period is too short or too warm.
    """
    records = list(records)
    base_stats = period_stats(records, base, method)
    target_stats = period_stats(records, target, method)
    _check(base_stats, method, min_days, min_dd, "base")
    _check(target_stats, method, min_days, min_dd, "target")
    k_base, k_target = base_stats.k, target_stats.k
    delta = (k_target - k_base) / k_base * 100.0 if k_base else 0.0
    return Comparison(
        base=base,
        target=target,
        method=method,
        k_base=k_base,
        k_target=k_target,
        delta_pct=delta,
        heat_base=base_stats.heat_space_kwh,
        heat_target=target_stats.heat_space_kwh,
        dd_base=base_stats.degree_days,
        dd_target=target_stats.degree_days,
        n_base=base_stats.n_days,
        n_target=target_stats.n_days,
    )


def measure_periods(
    measure_date: date, last_date: date, season_cfg: SeasonConfig | None = None
) -> tuple[Period, Period]:
    """Before/after periods of a measure: from the start of the previous season up to
    the day before the measure, and from the measure date to the end of the season that
    contains ``last_date`` (METHODS section 8.4)."""
    season = season_for(measure_date, season_cfg)
    previous = season_for(season.start - timedelta(days=1), season_cfg)
    before = Period(previous.start, measure_date - timedelta(days=1), label="before")
    after_end = max(season_for(last_date, season_cfg).end, season.end)
    after = Period(measure_date, after_end, label="after")
    return before, after


def measure_effect(
    records: Iterable[DailyRecord],
    measure_date: date,
    season_cfg: SeasonConfig | None = None,
    climatology: Climatology | None = None,
    method: str = "classic",
    tac_key: str = "tac_house",
    fit_wind: bool = True,
    n_boot: int = 200,
    seed: int = 42,
    min_days: int = 30,
) -> tuple[Comparison, SignatureFit | None, SignatureFit | None]:
    """Effect of a measure: signature fits before/after with NAC saving (primary, needs a
    climatology) and the simple k comparison (secondary). Returns the comparison and
    the two fits (None when a fit was not possible)."""
    records = sorted(records, key=lambda r: r.date)
    if not records:
        raise InsufficientDataError("no records")
    before, after = measure_periods(measure_date, records[-1].date, season_cfg)
    comparison = compare_periods(records, before, after, method, min_days)

    fit_before = fit_signature(records, before, tac_key, fit_wind, min_days=min_days)
    fit_after = fit_signature(records, after, tac_key, fit_wind, min_days=min_days)
    if climatology is None or fit_before is None or fit_after is None:
        _LOGGER.debug("measure effect: NAC saving not available (fit or climatology missing)")
        return comparison, fit_before, fit_after

    window = season_for(measure_date, season_cfg)
    saving, interval = saving_between(
        fit_before, fit_after, climatology, records, records, n_boot, seed, window
    )
    comparison = replace(
        comparison,
        nac_base=normalized_consumption(fit_before, climatology, window),
        nac_target=normalized_consumption(fit_after, climatology, window),
        saving_pct=saving,
        ci95_saving=interval,
    )
    return comparison, fit_before, fit_after
