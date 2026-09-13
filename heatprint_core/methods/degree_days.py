"""Degree-day methods (METHODS section 4).

Every method yields a non-negative number per day. All methods are always computed
(ADR 0004); the user picks which ones are shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import KNMI14_BASE_TEMP, MONTH_WEIGHTS
from ..flags import Flag
from ..models import ClassicParams, DailyWeather, MethodConfig, PblParams
from .effective_temperature import preset, t_eff, tac_for_day, weather_partial
from .pbl_params import pbl_params


def dd_classic(
    t_ref: float, month: int, params: ClassicParams | None = None
) -> tuple[float, float]:
    """Classic (mindergas-compatible) degree days (METHODS section 4.1).

    Returns ``(weighted, unweighted)``. With ``params.weighted`` False both values are
    equal to the unweighted degree days.

    ::

        DD  = max(0, T_base - t_ref)   if t_ref < T_limit else 0
        WDD = DD * w_month
    """
    params = params or ClassicParams()
    unweighted = max(0.0, params.base_temp - t_ref) if t_ref < params.heating_limit else 0.0
    weighted = unweighted * MONTH_WEIGHTS[month] if params.weighted else unweighted
    return weighted, unweighted


def dd_knmi14(t_eff_knmi: float) -> float:
    """KNMI gas-year degree days ``max(0, 14 - T_eff_knmi)`` (METHODS section 4.2)."""
    return max(0.0, KNMI14_BASE_TEMP - t_eff_knmi)


def dd_pbl(tac: float, month: int, params: PblParams | None = None) -> float:
    """PBL / KEV-SJV degree days ``RER_m * max(0, TST_m - TAC)`` [+ TOP_m] (METHODS 4.3)."""
    params = params or PblParams()
    month_params = pbl_params(month, params.parameter_set)
    value = month_params.rer * max(0.0, month_params.tst - tac)
    if params.include_top:
        value += month_params.top
    return value


def dd_house(tac: float, balance_temp: float) -> float:
    """House-specific degree days ``max(0, T_b - TAC_house)`` (METHODS section 4.4)."""
    return max(0.0, balance_temp - tac)


@dataclass
class DayMethods:
    """All degree-day values and intermediate temperatures of one day."""

    dd: dict[str, float]
    t_eff_knmi: float
    tac_pbl: float
    tac_house: float
    flags: set[Flag] = field(default_factory=set)

    def as_dict(self) -> dict[str, float]:
        """Flat dict with the degree days and the intermediate temperatures."""
        result = dict(self.dd)
        result["t_eff_knmi"] = self.t_eff_knmi
        result["tac_pbl"] = self.tac_pbl
        result["tac_house"] = self.tac_house
        return result


def compute_day(
    today: DailyWeather,
    yesterday: DailyWeather | None,
    method_config: MethodConfig | None = None,
    house_balance_temp: float | None = None,
) -> DayMethods:
    """Compute every method for one day (METHODS sections 3 and 4).

    ``yesterday`` is the weather of the previous calendar day (None if unknown).
    ``house_balance_temp`` is the balance temperature of the latest signature fit; when
    None the house method falls back to ``T_b = 15.5`` on the PBL preset (without RER)
    and the day is flagged ``HOUSE_NOT_FITTED``. ``tac_house`` is always the TAC of the
    house preset (inertia weights, no wind term), the basis of the fit in section 7.
    """
    cfg = method_config or MethodConfig()
    flags: set[Flag] = set()
    month = today.date.month

    # Classic: t_mean by default, or the effective temperature of a preset.
    if cfg.classic.t_ref == "t_mean":
        t_ref = today.t_mean
    else:
        classic_preset = preset(
            cfg.classic.t_ref,
            pbl_wind_mode=cfg.pbl.wind_mode,
            include_sun=cfg.pbl.include_sun,
            wind_sqrt_coef=cfg.pbl.wind_sqrt_coef,
            tac_weights=cfg.house.tac_weights,
        )
        t_ref = t_eff(today, classic_preset)
        if weather_partial(today, classic_preset):
            flags.add(Flag.WEATHER_PARTIAL)
    classic_weighted, classic_unweighted = dd_classic(t_ref, month, cfg.classic)

    # KNMI 14 degrees (effective temperature T - wind/1.5, no inertia).
    knmi_preset = preset("knmi")
    t_eff_knmi = t_eff(today, knmi_preset)
    if weather_partial(today, knmi_preset):
        flags.add(Flag.WEATHER_PARTIAL)

    # PBL: wind (linear or sqrt), optional sun, inertia 0.65/0.35.
    pbl_preset = preset(
        "pbl",
        pbl_wind_mode=cfg.pbl.wind_mode,
        include_sun=cfg.pbl.include_sun,
        wind_sqrt_coef=cfg.pbl.wind_sqrt_coef,
    )
    pbl_point = tac_for_day(today, yesterday, pbl_preset)
    if pbl_point.partial:
        flags.add(Flag.WEATHER_PARTIAL)

    # House: inertia only; wind sensitivity lives in the fit (METHODS section 7).
    house_preset = preset("house", tac_weights=cfg.house.tac_weights)
    house_point = tac_for_day(today, yesterday, house_preset)
    if house_point.partial:
        flags.add(Flag.WEATHER_PARTIAL)

    if house_balance_temp is None:
        house = dd_house(pbl_point.tac, cfg.house.fallback_balance_temp)
        flags.add(Flag.HOUSE_NOT_FITTED)
    else:
        house = dd_house(house_point.tac, house_balance_temp)

    dd = {
        "classic": classic_weighted,
        "classic_unweighted": classic_unweighted,
        "knmi14": dd_knmi14(t_eff_knmi),
        "pbl": dd_pbl(pbl_point.tac, month, cfg.pbl),
        "house": house,
    }
    return DayMethods(
        dd=dd,
        t_eff_knmi=t_eff_knmi,
        tac_pbl=pbl_point.tac,
        tac_house=house_point.tac,
        flags=flags,
    )


def compute_all(
    weather_today: DailyWeather,
    weather_yesterday: DailyWeather | None,
    method_config: MethodConfig | None = None,
    house_balance_temp: float | None = None,
) -> dict[str, float]:
    """Flat dict with ``classic``, ``classic_unweighted``, ``knmi14``, ``pbl``, ``house``
    and the intermediate temperatures ``t_eff_knmi``, ``tac_pbl``, ``tac_house``.

    See :func:`compute_day` for the flags.
    """
    return compute_day(
        weather_today, weather_yesterday, method_config, house_balance_temp
    ).as_dict()
