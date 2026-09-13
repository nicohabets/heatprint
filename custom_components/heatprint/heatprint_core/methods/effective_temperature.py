"""Effective temperature family and thermal-inertia weighting (METHODS section 3).

::

    T_eff(d) = t_mean(d) - c_lin * wind(d) - c_sqrt * sqrt(wind(d)) + c_sun * radiation(d)
    TAC(d)   = w_0 * T_eff(d) + w_1 * T_eff(d-1)          (w_0 + w_1 = 1)

Missing wind or radiation makes the corresponding term fall back to zero (the
temperature-only variant) and marks the day as partial (flag ``WEATHER_PARTIAL``).
A missing previous day gives ``TAC(d) = T_eff(d)``, also partial.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from ..constants import KNMI_WIND_DIVISOR, PBL_SUN_COEF, PBL_TAC_WEIGHTS, PBL_WIND_SQRT_COEF
from ..models import DailyWeather

PRESET_NAMES: tuple[str, ...] = ("none", "knmi", "pbl", "house")


@dataclass(frozen=True)
class EffectivePreset:
    """Coefficients of one effective-temperature preset (METHODS section 3, table)."""

    name: str
    c_lin: float = 0.0
    c_sqrt: float = 0.0
    c_sun: float = 0.0
    w0: float = 1.0
    w1: float = 0.0

    @property
    def uses_wind(self) -> bool:
        """True when the preset has a wind term."""
        return self.c_lin != 0.0 or self.c_sqrt != 0.0

    @property
    def uses_sun(self) -> bool:
        """True when the preset has a solar term."""
        return self.c_sun != 0.0

    @property
    def uses_history(self) -> bool:
        """True when yesterday's effective temperature contributes to TAC."""
        return self.w1 != 0.0


def preset(
    name: str,
    pbl_wind_mode: str = "linear",
    include_sun: bool = False,
    wind_sqrt_coef: float = PBL_WIND_SQRT_COEF,
    tac_weights: tuple[float, float] = PBL_TAC_WEIGHTS,
) -> EffectivePreset:
    """Return the preset ``none``, ``knmi``, ``pbl`` or ``house`` (METHODS section 3).

    - ``none``: bare daily mean temperature (mindergas, classic degree days).
    - ``knmi``: ``T - wind / 1.5`` (KNMI gas-year degree days).
    - ``pbl``: wind linear (``1/1.5``) or square root (``wind_sqrt_coef``) depending on
      ``pbl_wind_mode``; optional solar term ``1/480``; inertia weights ``tac_weights``.
    - ``house``: no wind term (wind sensitivity is fitted separately, METHODS section 7);
      inertia weights ``tac_weights``.
    """
    if name == "none":
        return EffectivePreset(name="none")
    if name == "knmi":
        return EffectivePreset(name="knmi", c_lin=1 / KNMI_WIND_DIVISOR)
    if name == "pbl":
        if pbl_wind_mode == "sqrt":
            c_lin, c_sqrt = 0.0, wind_sqrt_coef
        elif pbl_wind_mode == "linear":
            c_lin, c_sqrt = 1 / KNMI_WIND_DIVISOR, 0.0
        else:
            raise ValueError(f"unknown pbl_wind_mode: {pbl_wind_mode!r}")
        return EffectivePreset(
            name="pbl",
            c_lin=c_lin,
            c_sqrt=c_sqrt,
            c_sun=PBL_SUN_COEF if include_sun else 0.0,
            w0=tac_weights[0],
            w1=tac_weights[1],
        )
    if name == "house":
        return EffectivePreset(name="house", w0=tac_weights[0], w1=tac_weights[1])
    raise ValueError(f"unknown preset: {name!r}")


def weather_partial(weather: DailyWeather, preset: EffectivePreset) -> bool:
    """True when the preset needs wind or radiation that ``weather`` lacks."""
    if preset.uses_wind and weather.wind_mean is None:
        return True
    return preset.uses_sun and weather.radiation is None


def t_eff(weather: DailyWeather, preset: EffectivePreset) -> float:
    """Effective temperature of one day; missing wind/radiation terms fall back to zero."""
    value = weather.t_mean
    wind = weather.wind_mean
    if wind is not None and preset.uses_wind:
        wind = max(0.0, wind)
        value -= preset.c_lin * wind + preset.c_sqrt * math.sqrt(wind)
    if weather.radiation is not None and preset.uses_sun:
        value += preset.c_sun * max(0.0, weather.radiation)
    return value


@dataclass(frozen=True)
class TacPoint:
    """Effective temperature and TAC of one day."""

    date: date
    t_eff: float
    tac: float
    #: True when wind/radiation/yesterday was missing (flag ``WEATHER_PARTIAL``).
    partial: bool


def tac_for_day(
    today: DailyWeather, yesterday: DailyWeather | None, preset: EffectivePreset
) -> TacPoint:
    """TAC of ``today`` using ``yesterday`` for the inertia term.

    ``yesterday`` must be the weather of the calendar day before ``today``; when it is
    None (or a different date) the TAC equals today's effective temperature and the
    point is marked partial (METHODS section 3, last paragraph).
    """
    today_eff = t_eff(today, preset)
    partial = weather_partial(today, preset)
    if not preset.uses_history:
        return TacPoint(today.date, today_eff, today_eff, partial)
    if yesterday is None or yesterday.date != today.date - timedelta(days=1):
        return TacPoint(today.date, today_eff, today_eff, True)
    yesterday_eff = t_eff(yesterday, preset)
    partial = partial or weather_partial(yesterday, preset)
    tac = preset.w0 * today_eff + preset.w1 * yesterday_eff
    return TacPoint(today.date, today_eff, tac, partial)


def tac_series(weathers: Iterable[DailyWeather], preset: EffectivePreset) -> list[TacPoint]:
    """TAC for a series of days (sorted by date internally, duplicates: last wins)."""
    by_date: dict[date, DailyWeather] = {}
    for weather in weathers:
        by_date[weather.date] = weather
    result: list[TacPoint] = []
    for day in sorted(by_date):
        result.append(tac_for_day(by_date[day], by_date.get(day - timedelta(days=1)), preset))
    return result
