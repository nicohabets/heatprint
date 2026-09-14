"""Cost and CO₂ of a generator-day (METHODS section 13).

The Home Assistant layer reads daily (and, for ``price_mode: dynamic``, hourly)
series from the recorder and passes them here. This module stays free of HA
imports (ADR 0001) and of forecast-attribute adapters (ADR 0006).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .flags import Flag
from .models import DailyEnergy, Generator, GeneratorKind, PriceMode

ELECTRIC_KINDS = frozenset(
    {GeneratorKind.HEAT_PUMP, GeneratorKind.ELECTRIC_HEATER, GeneratorKind.AIR_TO_AIR}
)

HourlyDay = Mapping[Any, float]


def billed_amount(generator: Generator, energy: DailyEnergy) -> float | None:
    """Carrier amount billed that day (electric kWh for electric kinds)."""
    if generator.kind in ELECTRIC_KINDS:
        return energy.electric_kwh
    return energy.carrier_amount


def hourly_cost(electric_kwh: HourlyDay | None, price: HourlyDay | None) -> float | None:
    """``Σ_h electric_kwh(h) * price(h)`` over intersecting hour keys (METHODS 13.2).

    Returns None when either series is missing or they share no hour.
    """
    if not electric_kwh or not price:
        return None
    total = 0.0
    matched = 0
    for hour, kwh in electric_kwh.items():
        if hour not in price:
            continue
        total += float(kwh) * float(price[hour])
        matched += 1
    if matched == 0:
        return None
    return total


def mean_of(series: HourlyDay | None) -> float | None:
    """Arithmetic mean of a mapping of hour values; None when empty."""
    if not series:
        return None
    values = [float(value) for value in series.values()]
    if not values:
        return None
    return sum(values) / len(values)


def generator_cost(
    generator: Generator,
    energy: DailyEnergy,
    *,
    daily_price: float | None,
    hourly_electric: HourlyDay | None = None,
    hourly_price: HourlyDay | None = None,
) -> tuple[float | None, set[Flag]]:
    """Cost of one generator on one day (METHODS 13.1 / 13.2).

    Dynamic mode is only applied for electric kinds. When hourly statistics
    are incomplete the day's mean price (or the supplied daily price) is used
    and ``PRICE_ESTIMATED_FLAT`` is set.
    """
    flags: set[Flag] = set()
    billed = billed_amount(generator, energy)
    wants_dynamic = (
        generator.price_mode is PriceMode.DYNAMIC and generator.kind in ELECTRIC_KINDS
    )
    if wants_dynamic:
        dynamic = hourly_cost(hourly_electric, hourly_price)
        if dynamic is not None:
            return dynamic, flags
        flags.add(Flag.PRICE_ESTIMATED_FLAT)
        fallback_price = daily_price
        if fallback_price is None:
            fallback_price = mean_of(hourly_price)
        if billed is None or fallback_price is None:
            return None, flags
        return float(billed) * float(fallback_price), flags
    if billed is None or daily_price is None:
        return None, flags
    return float(billed) * float(daily_price), flags


def space_share_of_cost(energy: DailyEnergy, cost: float | None) -> float | None:
    """Restrict a generator's cost to its space-heating share (METHODS 12.5)."""
    if cost is None:
        return None
    total = energy.heat_total_kwh
    if total <= 0:
        return float(cost) if energy.heat_space_kwh > 0 else 0.0
    return float(cost) * (energy.heat_space_kwh / total)


def site_default_price(cost_space_eur: float | None, heat_space_kwh: float) -> float | None:
    """€/kWh implied by the day's allocated space-heating cost (metered rooms)."""
    if cost_space_eur is None or heat_space_kwh <= 0:
        return None
    return float(cost_space_eur) / float(heat_space_kwh)
