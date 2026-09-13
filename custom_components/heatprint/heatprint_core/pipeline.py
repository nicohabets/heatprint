"""Daily pipeline: weather + energy per generator -> :class:`DailyRecord` (ARCHITECTURE section 3).

For every calendar day between the first and last day with weather or energy data:

1. Effective temperatures and all degree-day methods (METHODS sections 3 and 4).
2. Per generator: carrier -> heat (section 5), DHW split (section 6), daily COP.
3. Aggregation: heat, carriers, heat pump share, optional cost and CO2, flags (section 10).

Energy input series map a date to ``(amount, flags)`` as produced by
:func:`heatprint_core.readings.readings_to_daily`; plain floats are accepted too.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from .constants import GJ_TO_KWH
from .dhw import estimate_baseline, split_dhw
from .flags import Flag
from .heat import carrier_to_heat, cop_day
from .methods.degree_days import compute_day
from .models import (
    CarrierUnit,
    DailyEnergy,
    DailyRecord,
    DailyWeather,
    DhwMode,
    Generator,
    GeneratorKind,
    Role,
    SignatureFit,
    Site,
    default_co2_factor,
)

_LOGGER = logging.getLogger(__name__)

DailySeries = Mapping[date, tuple[float, set[Flag]] | float]
PriceSeries = Mapping[str, float | Mapping[date, float]]

ELECTRIC_KINDS = frozenset(
    {GeneratorKind.HEAT_PUMP, GeneratorKind.ELECTRIC_HEATER, GeneratorKind.AIR_TO_AIR}
)


def _entry(series: DailySeries | None, day: date) -> tuple[float | None, set[Flag]]:
    """Amount and flags of ``series`` on ``day`` (``(None, set())`` when absent)."""
    if series is None:
        return None, set()
    value = series.get(day)
    if value is None:
        return None, set()
    if isinstance(value, tuple):
        amount, flags = value
        return float(amount), set(flags)
    return float(value), set()


def _series_range(*series: DailySeries | None) -> tuple[date, date] | None:
    days = [day for s in series if s for day in s]
    if not days:
        return None
    return min(days), max(days)


def _price_at(prices: PriceSeries | None, generator_id: str, day: date) -> float | None:
    if not prices:
        return None
    value = prices.get(generator_id)
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(day)
    return float(value)


def estimate_baselines(
    site: Site,
    energy_by_generator: Mapping[str, DailySeries],
    thermal_by_generator: Mapping[str, DailySeries] | None = None,
    min_days: int = 30,
) -> dict[str, float | None]:
    """DHW baseline per generator (METHODS section 6).

    The baseline is in carrier units when the generator has a carrier (``energy``)
    series; for a heat pump with only a thermal series it is in kWh of heat.
    Generators that need no baseline map to None.
    """
    result: dict[str, float | None] = {}
    for generator in site.generators:
        series = energy_by_generator.get(generator.id)
        if not series and thermal_by_generator:
            series = thermal_by_generator.get(generator.id)
        if not series:
            result[generator.id] = None
            continue
        amounts = {day: _entry(series, day)[0] or 0.0 for day in series}
        result[generator.id] = estimate_baseline(
            amounts, generator.dhw.summer_start, generator.dhw.summer_end, min_days
        )
    return result


def build_daily_records(
    site: Site,
    weather_by_date: Mapping[date, DailyWeather],
    energy_by_generator: Mapping[str, DailySeries],
    thermal_by_generator: Mapping[str, DailySeries] | None = None,
    electric_by_generator: Mapping[str, DailySeries] | None = None,
    dhw_by_generator: Mapping[str, DailySeries] | None = None,
    baselines: Mapping[str, float | None] | None = None,
    house_fit: SignatureFit | None = None,
    prices: PriceSeries | None = None,
    co2_factors: PriceSeries | None = None,
    outlier_dates: Iterable[date] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> list[DailyRecord]:
    """Build one :class:`DailyRecord` per calendar day.

    Parameters:

    - ``energy_by_generator``: carrier amount per day per generator id (m3 gas, kWh
      electricity for heat pumps, GJ district heat).
    - ``thermal_by_generator`` / ``electric_by_generator`` / ``dhw_by_generator``:
      measured heat, electricity and DHW heat (kWh) of heat pumps per day.
    - ``baselines``: DHW baseline per generator (see :func:`estimate_baselines`); when
      None the baselines are estimated from the given series.
    - ``house_fit``: latest signature fit; its balance temperature drives the ``house``
      method. Without it the house method uses its fallback (flag ``HOUSE_NOT_FITTED``).
    - ``prices`` / ``co2_factors``: per generator a price (EUR) or factor (kg) per carrier
      unit (per electric kWh for electric kinds), as a constant or per-day mapping.
    - ``outlier_dates``: days flagged ``OUTLIER`` by the latest fit.

    A day is ``ENERGY_MISSING`` when no generator has data, or when a generator lacks
    data inside its own data range (a generator that starts later or stops earlier is
    simply absent on the other days, so the history stays usable).
    """
    thermal_by_generator = thermal_by_generator or {}
    electric_by_generator = electric_by_generator or {}
    dhw_by_generator = dhw_by_generator or {}
    outliers = set(outlier_dates or ())
    if baselines is None:
        baselines = estimate_baselines(site, energy_by_generator, thermal_by_generator)

    ranges: dict[str, tuple[date, date] | None] = {}
    baseline_in_kwh: dict[str, bool] = {}
    for generator in site.generators:
        ranges[generator.id] = _series_range(
            energy_by_generator.get(generator.id),
            thermal_by_generator.get(generator.id),
            electric_by_generator.get(generator.id),
        )
        baseline_in_kwh[generator.id] = not energy_by_generator.get(generator.id) and bool(
            thermal_by_generator.get(generator.id)
        )

    all_days = set(weather_by_date)
    for series in (energy_by_generator, thermal_by_generator, electric_by_generator):
        for generator_series in series.values():
            all_days.update(generator_series)
    if start is not None:
        all_days = {d for d in all_days if d >= start}
    if end is not None:
        all_days = {d for d in all_days if d <= end}
    if not all_days:
        return []
    first, last = min(all_days), max(all_days)

    balance_temp = house_fit.balance_temp if house_fit is not None else None
    records: list[DailyRecord] = []
    day = first
    while day <= last:
        records.append(
            _build_record(
                site,
                day,
                weather_by_date.get(day),
                weather_by_date.get(day - timedelta(days=1)),
                energy_by_generator,
                thermal_by_generator,
                electric_by_generator,
                dhw_by_generator,
                baselines,
                baseline_in_kwh,
                ranges,
                balance_temp,
                prices,
                co2_factors,
                day in outliers,
            )
        )
        day += timedelta(days=1)
    _LOGGER.debug("built %d daily records for site %s (%s..%s)", len(records), site.id, first, last)
    return records


def _build_record(
    site: Site,
    day: date,
    weather: DailyWeather | None,
    weather_yesterday: DailyWeather | None,
    energy_by_generator: Mapping[str, DailySeries],
    thermal_by_generator: Mapping[str, DailySeries],
    electric_by_generator: Mapping[str, DailySeries],
    dhw_by_generator: Mapping[str, DailySeries],
    baselines: Mapping[str, float | None],
    baseline_in_kwh: Mapping[str, bool],
    ranges: Mapping[str, tuple[date, date] | None],
    balance_temp: float | None,
    prices: PriceSeries | None,
    co2_factors: PriceSeries | None,
    is_outlier: bool,
) -> DailyRecord:
    record = DailyRecord(date=day, site_id=site.id)
    flags: set[Flag] = set()

    # --- weather and methods -----------------------------------------------------------------
    if weather is None:
        flags.add(Flag.WEATHER_MISSING)
    else:
        methods = compute_day(weather, weather_yesterday, site.methods, balance_temp)
        record.t_mean = weather.t_mean
        record.wind_mean = weather.wind_mean
        record.radiation = weather.radiation
        record.t_min = weather.t_min
        record.t_max = weather.t_max
        record.t_eff_knmi = methods.t_eff_knmi
        record.tac_pbl = methods.tac_pbl
        record.tac_house = methods.tac_house
        record.dd = methods.dd
        flags |= methods.flags
        if weather.provisional:
            flags.add(Flag.WEATHER_PROVISIONAL)

    # --- energy per generator -----------------------------------------------------------------
    any_data = False
    heat_pump_space = 0.0
    cost: float | None = None
    co2: float | None = None
    for generator in site.generators:
        energy = _generator_energy(
            generator,
            day,
            weather,
            energy_by_generator.get(generator.id),
            thermal_by_generator.get(generator.id),
            electric_by_generator.get(generator.id),
            dhw_by_generator.get(generator.id),
            baselines.get(generator.id),
            baseline_in_kwh.get(generator.id, False),
        )
        if energy is None:
            data_range = ranges.get(generator.id)
            if data_range is not None and data_range[0] <= day <= data_range[1]:
                flags.add(Flag.ENERGY_MISSING)
            continue
        any_data = True
        record.heat_by_generator[generator.id] = energy
        record.heat_space_kwh += energy.heat_space_kwh
        record.heat_dhw_kwh += energy.heat_dhw_kwh
        if energy.electric_kwh is not None:
            record.electric_kwh += energy.electric_kwh
        if (
            generator.kind is GeneratorKind.GAS_BOILER
            and generator.carrier.unit is CarrierUnit.M3
            and energy.carrier_amount is not None
        ):
            record.gas_m3 += energy.carrier_amount
        if generator.kind is GeneratorKind.DISTRICT_HEAT and energy.carrier_amount is not None:
            if generator.carrier.unit is CarrierUnit.GJ:
                record.district_gj += energy.carrier_amount
            elif generator.carrier.unit is CarrierUnit.KWH:
                record.district_gj += energy.carrier_amount / GJ_TO_KWH
        if generator.is_heat_pump:
            heat_pump_space += energy.heat_space_kwh
        flags |= energy.flags

        billed = energy.electric_kwh if generator.kind in ELECTRIC_KINDS else energy.carrier_amount
        if billed is not None:
            price = _price_at(prices, generator.id, day)
            if price is not None:
                cost = (cost or 0.0) + billed * price
            factor = _price_at(co2_factors, generator.id, day)
            if factor is None:
                factor = generator.co2_factor
            if factor is None:
                factor = default_co2_factor(generator.kind, generator.carrier.unit)
            if factor is not None:
                co2 = (co2 or 0.0) + billed * factor

    if not any_data:
        flags.add(Flag.ENERGY_MISSING)
    if record.heat_space_kwh > 0:
        record.share_heat_pump = heat_pump_space / record.heat_space_kwh
    record.cost_eur = cost
    record.co2_kg = co2
    if is_outlier:
        flags.add(Flag.OUTLIER)
    record.flags = flags
    return record


def _generator_energy(
    generator: Generator,
    day: date,
    weather: DailyWeather | None,
    energy_series: DailySeries | None,
    thermal_series: DailySeries | None,
    electric_series: DailySeries | None,
    dhw_series: DailySeries | None,
    baseline: float | None,
    baseline_is_kwh: bool,
) -> DailyEnergy | None:
    """Heat of one generator on one day; None when the generator has no data that day."""
    carrier, flags = _entry(energy_series, day)
    thermal, thermal_flags = _entry(thermal_series, day)
    electric, electric_flags = _entry(electric_series, day)
    measured_dhw, dhw_flags = _entry(dhw_series, day)
    if carrier is None and thermal is None and electric is None:
        return None
    flags |= thermal_flags | electric_flags | dhw_flags

    heat_total, electric_kwh, heat_flags = carrier_to_heat(
        generator,
        carrier,
        electric_kwh=electric,
        thermal_kwh=thermal,
        t_mean=weather.t_mean if weather is not None else None,
    )
    flags |= heat_flags
    heat_dhw, heat_space = split_dhw(
        generator,
        heat_total,
        carrier,
        baseline,
        measured_dhw_kwh=measured_dhw,
        baseline_in_kwh=baseline_is_kwh,
    )
    uses_baseline = generator.role is Role.BOTH and (
        generator.dhw.mode is DhwMode.BASELINE
        or (generator.dhw.mode is DhwMode.MEASURED and measured_dhw is None)
    )
    if uses_baseline and baseline is None:
        flags.add(Flag.DHW_BASELINE_MISSING)
    return DailyEnergy(
        date=day,
        generator_id=generator.id,
        carrier_amount=carrier,
        electric_kwh=electric_kwh,
        heat_total_kwh=heat_total,
        heat_dhw_kwh=heat_dhw,
        heat_space_kwh=heat_space,
        cop_day=cop_day(thermal, electric_kwh),
        flags=flags,
    )
