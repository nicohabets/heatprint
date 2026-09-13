"""Carrier to heat per generator kind (METHODS section 5)."""

from __future__ import annotations

import pytest

from heatprint_core.flags import Flag
from heatprint_core.heat import carrier_to_heat, cop_day, heat_to_carrier, static_heat_per_unit
from heatprint_core.models import (
    CarrierInput,
    CarrierUnit,
    Conversion,
    ConversionMode,
    Generator,
    GeneratorKind,
    Role,
)


def test_gas_boiler_hs_and_hi() -> None:
    boiler = Generator.for_kind("b", "CV", GeneratorKind.GAS_BOILER)
    heat, electric, flags = carrier_to_heat(boiler, 10.0)
    assert heat == pytest.approx(10 * 8.792 * 0.95)
    assert electric == 0.0 and flags == set()
    hi_boiler = Generator.for_kind(
        "b",
        "CV",
        GeneratorKind.GAS_BOILER,
        conversion=Conversion(heating_value=7.92, efficiency=0.9),
    )
    assert carrier_to_heat(hi_boiler, 10.0)[0] == pytest.approx(10 * 7.92 * 0.9)
    assert carrier_to_heat(boiler, None)[0] == 0.0


def test_heat_pump_measured_and_estimated() -> None:
    heat_pump = Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE)
    heat, electric, flags = carrier_to_heat(heat_pump, 10.0)
    assert heat == pytest.approx(35.0) and electric == 10.0
    assert flags == {Flag.HEAT_ESTIMATED}
    heat, electric, flags = carrier_to_heat(heat_pump, 10.0, thermal_kwh=32.0)
    assert heat == 32.0 and electric == 10.0 and flags == set()
    # Separate electric counter overrides the carrier amount.
    heat, electric, flags = carrier_to_heat(heat_pump, None, electric_kwh=8.0, thermal_kwh=30.0)
    assert (heat, electric) == (30.0, 8.0)
    # Thermal only: electricity unknown.
    heat, electric, flags = carrier_to_heat(heat_pump, None, thermal_kwh=30.0)
    assert heat == 30.0 and electric is None


def test_heat_pump_cop_curve() -> None:
    heat_pump = Generator.for_kind(
        "hp",
        "WP",
        GeneratorKind.HEAT_PUMP,
        conversion=Conversion(mode=ConversionMode.COP_CURVE, cop_curve_a=2.2, cop_curve_b=0.08),
    )
    heat, _electric, flags = carrier_to_heat(heat_pump, 10.0, t_mean=5.0)
    assert heat == pytest.approx(10 * (2.2 + 0.08 * 5.0))
    assert Flag.HEAT_ESTIMATED in flags
    # Without a temperature the curve falls back to the SCOP.
    assert carrier_to_heat(heat_pump, 10.0)[0] == pytest.approx(35.0)


def test_electric_heater_and_air_to_air() -> None:
    heater = Generator.for_kind("eh", "Kachel", GeneratorKind.ELECTRIC_HEATER)
    assert carrier_to_heat(heater, 2.0) == (2.0, 2.0, set())
    air = Generator.for_kind("aa", "Airco", GeneratorKind.AIR_TO_AIR)
    heat, electric, flags = carrier_to_heat(air, 2.0)
    assert heat == pytest.approx(6.0) and electric == 2.0
    assert flags == {Flag.HEAT_ESTIMATED}
    assert carrier_to_heat(air, 2.0, thermal_kwh=5.0)[0] == 5.0


def test_district_heat_gj_and_kwh() -> None:
    district = Generator.for_kind("dh", "Warmtenet", GeneratorKind.DISTRICT_HEAT)
    heat, electric, flags = carrier_to_heat(district, 0.5)
    assert heat == pytest.approx(0.5 * 277.78)
    assert electric == 0.0 and flags == set()
    kwh_meter = Generator.for_kind(
        "dh", "Warmtenet", GeneratorKind.DISTRICT_HEAT, carrier=CarrierInput(unit=CarrierUnit.KWH)
    )
    assert carrier_to_heat(kwh_meter, 100.0)[0] == pytest.approx(100.0)
    lossy = Generator.for_kind(
        "dh", "Warmtenet", GeneratorKind.DISTRICT_HEAT, conversion=Conversion(efficiency=0.9)
    )
    assert carrier_to_heat(lossy, 1.0)[0] == pytest.approx(277.78 * 0.9)


def test_other_with_factor() -> None:
    pellet = Generator.for_kind(
        "p",
        "Pellet",
        GeneratorKind.OTHER,
        conversion=Conversion(mode=ConversionMode.FACTOR, factor=4.5),
        carrier=CarrierInput(unit=CarrierUnit.M3),
    )
    heat, electric, flags = carrier_to_heat(pellet, 2.0)
    assert heat == pytest.approx(2.0 * 8.792 * 4.5)
    assert electric == 0.0 and flags == set()
    electric_other = Generator.for_kind(
        "o",
        "Infrarood",
        GeneratorKind.OTHER,
        conversion=Conversion(mode=ConversionMode.FACTOR, factor=1.0),
    )
    assert carrier_to_heat(electric_other, 3.0) == (3.0, 3.0, set())


def test_cop_day_threshold() -> None:
    assert cop_day(32.0, 10.0) == pytest.approx(3.2)
    assert cop_day(1.0, 0.2) is None
    assert cop_day(1.0, 0.25) == pytest.approx(4.0)
    assert cop_day(None, 10.0) is None
    assert cop_day(10.0, None) is None


def test_static_conversions_round_trip() -> None:
    boiler = Generator.for_kind("b", "CV", GeneratorKind.GAS_BOILER)
    assert static_heat_per_unit(boiler) == pytest.approx(8.792 * 0.95)
    assert heat_to_carrier(boiler, 83.524) == pytest.approx(10.0)
    heat_pump = Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP)
    assert heat_to_carrier(heat_pump, 35.0) == pytest.approx(10.0)
