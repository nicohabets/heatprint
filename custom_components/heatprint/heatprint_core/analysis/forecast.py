"""Forecast of the running heating season (METHODS section 8.5).

::

    DD_rest    = sum of dd_clim[method](doy) over the remaining season days
    k_ytd      = Q_space_ytd / sum dd_ytd
    Q_forecast = Q_space_ytd + k_ytd * DD_rest        (space heating)
    DHW        = Q_dhw_ytd + Q_dhw_per_day * days_rest

With a valid signature fit a second variant sums the fitted model over the TAC
climatology. Per generator the remaining heat is split by the shares of the last 28
days; the year-to-date part per generator is known exactly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from ..flags import Flag, is_usable
from ..heat import heat_to_carrier
from ..models import Climatology, DailyRecord, Forecast, Season, SignatureFit, Site
from ..weather.climatology import climatology_value, remaining_season_dd

_LOGGER = logging.getLogger(__name__)

SHARE_WINDOW_DAYS = 28


def generator_shares_last_days(
    records: Iterable[DailyRecord], days: int = SHARE_WINDOW_DAYS, end: date | None = None
) -> dict[str, float]:
    """Share of total heat (space + DHW) per generator over the last ``days`` days with
    energy data (ending at ``end`` or the last record). Empty when there is no heat."""
    usable = [
        r for r in records if Flag.ENERGY_MISSING not in r.flags and (end is None or r.date <= end)
    ]
    usable.sort(key=lambda r: r.date)
    if not usable:
        return {}
    window_start = usable[-1].date - timedelta(days=days - 1)
    totals: dict[str, float] = {}
    for record in usable:
        if record.date < window_start:
            continue
        for generator_id, energy in record.heat_by_generator.items():
            totals[generator_id] = totals.get(generator_id, 0.0) + energy.heat_total_kwh
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return {}
    return {generator_id: value / grand_total for generator_id, value in totals.items()}


def forecast_season(
    records: Iterable[DailyRecord],
    season: Season,
    climatology: Climatology,
    method: str = "pbl",
    dhw_per_day: float = 0.0,
    generator_shares: Mapping[str, float] | None = None,
    fit: SignatureFit | None = None,
    today: date | None = None,
) -> Forecast:
    """Forecast heat for ``season`` from year-to-date records and the climatology.

    ``dhw_per_day`` is the expected DHW heat per remaining day (kWh, sum over
    generators). ``generator_shares`` defaults to the shares of the last 28 days. With a
    ``fit`` of the house preset and ``method == "house"`` the climatological house
    degree days use the fitted balance temperature when the climatology has none.
    """
    in_season = [
        r for r in records if season.contains(r.date) and (today is None or r.date < today)
    ]
    in_season.sort(key=lambda r: r.date)
    with_energy = [r for r in in_season if Flag.ENERGY_MISSING not in r.flags]
    usable = [r for r in in_season if is_usable(r.flags) and r.dd.get(method) is not None]

    heat_space_ytd = sum(r.heat_space_kwh for r in with_energy)
    heat_dhw_ytd = sum(r.heat_dhw_kwh for r in with_energy)
    dd_ytd = sum(r.dd[method] for r in in_season if r.dd.get(method) is not None)
    heat_usable = sum(r.heat_space_kwh for r in usable)
    dd_usable = sum(r.dd[method] for r in usable)
    k_ytd = heat_usable / dd_usable if dd_usable > 0 else None

    last_date = in_season[-1].date if in_season else season.start - timedelta(days=1)
    from_date = last_date + timedelta(days=1)
    days_remaining = max(0, (season.end - last_date).days)
    balance_temp = fit.balance_temp if fit is not None else None
    dd_remaining = remaining_season_dd(climatology, method, from_date, season.end, balance_temp)

    remaining_space = k_ytd * dd_remaining if k_ytd is not None else 0.0
    heat_space_forecast = heat_space_ytd + remaining_space

    heat_space_forecast_fit: float | None = None
    if fit is not None:
        model_remaining = 0.0
        day = from_date
        while day <= season.end:
            tac = climatology_value(climatology, "tac", day)
            if tac is not None:
                wind = climatology_value(climatology, "wind", day)
                model_remaining += max(0.0, fit.predict(tac, wind))
            day += timedelta(days=1)
        heat_space_forecast_fit = heat_space_ytd + model_remaining
        if k_ytd is None:
            heat_space_forecast = heat_space_forecast_fit
            remaining_space = model_remaining

    remaining_dhw = dhw_per_day * days_remaining
    heat_dhw_forecast = heat_dhw_ytd + remaining_dhw

    shares = (
        dict(generator_shares)
        if generator_shares is not None
        else generator_shares_last_days(in_season)
    )
    per_generator: dict[str, float] = {}
    ytd_by_generator: dict[str, float] = {}
    for record in with_energy:
        for generator_id, energy in record.heat_by_generator.items():
            ytd_by_generator[generator_id] = (
                ytd_by_generator.get(generator_id, 0.0) + energy.heat_total_kwh
            )
    for generator_id in set(shares) | set(ytd_by_generator):
        share = shares.get(generator_id, 0.0)
        per_generator[generator_id] = ytd_by_generator.get(generator_id, 0.0) + share * (
            remaining_space + remaining_dhw
        )

    _LOGGER.debug(
        "forecast %s (%s): ytd %.1f kWh, k %.3f, dd_rest %.1f -> %.1f kWh",
        season.label,
        method,
        heat_space_ytd,
        k_ytd or 0.0,
        dd_remaining,
        heat_space_forecast,
    )
    return Forecast(
        season=season,
        method=method,
        heat_space_ytd=heat_space_ytd,
        dd_ytd=dd_ytd,
        dd_remaining_clim=dd_remaining,
        heat_space_forecast=heat_space_forecast,
        per_generator=per_generator,
        k_ytd=k_ytd,
        days_ytd=len(in_season),
        days_remaining=days_remaining,
        heat_dhw_forecast=heat_dhw_forecast,
        heat_space_forecast_fit=heat_space_forecast_fit,
        last_date=last_date if in_season else None,
    )


def forecast_carrier_amounts(forecast: Forecast, site: Site) -> dict[str, float]:
    """Forecast per generator in carrier units (m3 gas, kWh electricity, GJ) using the
    static conversion of each generator (hybrid: gas m3 and heat pump kWh apart)."""
    result: dict[str, float] = {}
    for generator in site.generators:
        heat = forecast.per_generator.get(generator.id)
        if heat is None:
            continue
        result[generator.id] = heat_to_carrier(generator, heat)
    return result
