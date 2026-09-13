"""From energy carrier to delivered heat per generator per day (METHODS section 5).

| kind              | input             | heat total Q_total                        | electric E_el |
|-------------------|-------------------|-------------------------------------------|---------------|
| gas_boiler        | V m3              | V * HV * eta                              | 0             |
| heat_pump         | E_th and/or E_el  | E_th if measured, else E_el * SCOP (est.) | E_el          |
| electric_heater   | E_el              | E_el * 1.0                                | E_el          |
| air_to_air        | E_el              | E_el * COP (est.)                         | E_el          |
| district_heat     | H GJ (or kWh)     | H * 277.78 * eta                          | 0             |
| other             | x                 | x * factor                                | 0 or x        |
"""

from __future__ import annotations

from .constants import GJ_TO_KWH
from .flags import Flag
from .models import CarrierUnit, ConversionMode, Generator, GeneratorKind

#: Minimum electric energy per day for which a daily COP is reported (METHODS section 5).
COP_MIN_ELECTRIC_KWH: float = 0.2


def cop_day(
    thermal_kwh: float | None,
    electric_kwh: float | None,
    min_electric_kwh: float = COP_MIN_ELECTRIC_KWH,
) -> float | None:
    """Daily COP ``E_th / E_el``; None unless both are measured and ``E_el > 0.2 kWh``."""
    if thermal_kwh is None or electric_kwh is None or electric_kwh <= min_electric_kwh:
        return None
    return thermal_kwh / electric_kwh


def cop_from_curve(generator: Generator, t_mean: float | None) -> float:
    """COP of a ``cop_curve`` heat pump: ``a + b * t_mean`` (falls back to SCOP)."""
    conversion = generator.conversion
    if t_mean is None:
        return conversion.scop
    return max(1.0, conversion.cop_curve_a + conversion.cop_curve_b * t_mean)


def carrier_kwh(generator: Generator, carrier_amount: float) -> float:
    """Energy content of a carrier amount in kWh before efficiency (m3 -> HV, GJ -> 277.78)."""
    unit = generator.carrier.unit
    if unit is CarrierUnit.M3:
        return carrier_amount * generator.conversion.heating_value
    if unit is CarrierUnit.GJ:
        return carrier_amount * GJ_TO_KWH
    return carrier_amount


def carrier_to_heat(
    generator: Generator,
    carrier_amount: float | None,
    electric_kwh: float | None = None,
    thermal_kwh: float | None = None,
    t_mean: float | None = None,
) -> tuple[float, float | None, set[Flag]]:
    """Convert one day of carrier input into ``(heat_total_kwh, electric_kwh, flags)``.

    ``carrier_amount`` is the amount of the generator's ``energy_entity`` (m3 gas, kWh
    electricity for heat pumps, GJ district heat). ``electric_kwh`` overrides the
    electric amount of a heat pump when a separate electric counter exists;
    ``thermal_kwh`` is the measured heat of a heat pump. ``t_mean`` feeds the optional
    COP curve. Heat pump heat estimated via SCOP/COP carries ``HEAT_ESTIMATED``.
    """
    flags: set[Flag] = set()
    kind = generator.kind
    conversion = generator.conversion

    if kind is GeneratorKind.GAS_BOILER:
        amount = carrier_amount or 0.0
        return carrier_kwh(generator, amount) * conversion.efficiency, 0.0, flags

    if kind is GeneratorKind.DISTRICT_HEAT:
        amount = carrier_amount or 0.0
        return carrier_kwh(generator, amount) * conversion.efficiency, 0.0, flags

    if kind is GeneratorKind.HEAT_PUMP:
        electric = electric_kwh if electric_kwh is not None else carrier_amount
        if thermal_kwh is not None:
            # A measured thermal counter always wins, whatever the configured mode says.
            return thermal_kwh, electric, flags
        if electric is None:
            return 0.0, None, flags
        if conversion.mode is ConversionMode.COP_CURVE:
            cop = cop_from_curve(generator, t_mean)
        else:
            cop = conversion.scop
        flags.add(Flag.HEAT_ESTIMATED)
        return electric * cop, electric, flags

    if kind is GeneratorKind.ELECTRIC_HEATER:
        electric = electric_kwh if electric_kwh is not None else (carrier_amount or 0.0)
        return electric * 1.0, electric, flags

    if kind is GeneratorKind.AIR_TO_AIR:
        electric = electric_kwh if electric_kwh is not None else (carrier_amount or 0.0)
        if thermal_kwh is not None:
            return thermal_kwh, electric, flags
        flags.add(Flag.HEAT_ESTIMATED)
        return electric * conversion.cop, electric, flags

    # GeneratorKind.OTHER: x * factor; electric when the carrier is electricity (kWh).
    amount = carrier_amount or 0.0
    if electric_kwh is not None:
        electric_other: float | None = electric_kwh
    elif generator.carrier.unit is CarrierUnit.KWH:
        electric_other = amount
    else:
        electric_other = 0.0
    return carrier_kwh(generator, amount) * conversion.factor, electric_other, flags


def static_heat_per_unit(generator: Generator, t_mean: float | None = None) -> float:
    """Heat (kWh) delivered per carrier unit with the configured static conversion.

    Used to convert a DHW baseline in carrier units into kWh and to convert a heat
    forecast back into carrier units (``heat_to_carrier``).
    """
    heat, _electric, _flags = carrier_to_heat(generator, 1.0, t_mean=t_mean)
    return heat


def heat_to_carrier(generator: Generator, heat_kwh: float, t_mean: float | None = None) -> float:
    """Inverse static conversion: kWh of heat to carrier units (m3, kWh electric, GJ)."""
    per_unit = static_heat_per_unit(generator, t_mean)
    if per_unit <= 0:
        return 0.0
    return heat_kwh / per_unit
