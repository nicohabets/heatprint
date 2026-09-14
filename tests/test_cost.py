"""Cost and CO₂ (METHODS §13) including dynamic hourly tariffs (ADR 0006)."""

from __future__ import annotations

from datetime import date

import pytest

from heatprint_core.cost import (
    billed_amount,
    generator_cost,
    hourly_cost,
    mean_of,
    site_default_price,
    space_share_of_cost,
)
from heatprint_core.flags import Flag
from heatprint_core.models import (
    DailyEnergy,
    DailyRecord,
    DailyWeather,
    DemandKind,
    Generator,
    GeneratorKind,
    PriceMode,
    Role,
    Room,
    Site,
)
from heatprint_core.pipeline import build_daily_records
from heatprint_core.rooms import RoomDayInput, allocate_day, allocate_period

START = date(2026, 1, 15)


def _energy(
    *,
    carrier: float | None = None,
    electric: float | None = None,
    heat_total: float = 10.0,
    heat_dhw: float = 2.0,
    heat_space: float = 8.0,
) -> DailyEnergy:
    return DailyEnergy(
        date=START,
        generator_id="hp",
        carrier_amount=carrier,
        electric_kwh=electric,
        heat_total_kwh=heat_total,
        heat_dhw_kwh=heat_dhw,
        heat_space_kwh=heat_space,
    )


def test_hourly_cost_aligned_hours() -> None:
    electric = {0: 1.0, 1: 2.0, 2: 0.5}
    price = {0: 0.10, 1: 0.40, 2: 0.20}
    assert hourly_cost(electric, price) == pytest.approx(1.0 * 0.10 + 2.0 * 0.40 + 0.5 * 0.20)


def test_hourly_cost_intersection_and_empty() -> None:
    assert hourly_cost({0: 1.0}, {1: 0.2}) is None
    assert hourly_cost(None, {0: 0.2}) is None
    assert hourly_cost({0: 1.0}, None) is None
    assert hourly_cost({}, {0: 0.2}) is None


def test_mean_of_hourly() -> None:
    assert mean_of({0: 0.10, 1: 0.30}) == pytest.approx(0.20)
    assert mean_of({}) is None


def test_flat_generator_cost() -> None:
    boiler = Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)
    energy = _energy(carrier=5.0, heat_total=40.0, heat_dhw=4.0, heat_space=36.0)
    cost, flags = generator_cost(boiler, energy, daily_price=1.30)
    assert cost == pytest.approx(6.5)
    assert flags == set()
    assert billed_amount(boiler, energy) == 5.0
    assert space_share_of_cost(energy, cost) == pytest.approx(6.5 * 36.0 / 40.0)


def test_dynamic_hourly_then_flat_fallback() -> None:
    hp = Generator.for_kind(
        "hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE, price_mode=PriceMode.DYNAMIC
    )
    energy = _energy(electric=3.0, heat_total=10.5, heat_dhw=0.0, heat_space=10.5)
    hourly_e = {10: 1.0, 11: 2.0}
    hourly_p = {10: 0.05, 11: 0.40}
    cost, flags = generator_cost(
        hp, energy, daily_price=0.25, hourly_electric=hourly_e, hourly_price=hourly_p
    )
    assert cost == pytest.approx(1.0 * 0.05 + 2.0 * 0.40)
    assert Flag.PRICE_ESTIMATED_FLAT not in flags

    fallback, flags = generator_cost(
        hp, energy, daily_price=0.25, hourly_electric=None, hourly_price=hourly_p
    )
    assert fallback == pytest.approx(3.0 * 0.25)
    assert Flag.PRICE_ESTIMATED_FLAT in flags

    from_mean, flags = generator_cost(
        hp, energy, daily_price=None, hourly_electric={0: 1.0}, hourly_price=hourly_p
    )
    assert from_mean == pytest.approx(3.0 * mean_of(hourly_p))
    assert Flag.PRICE_ESTIMATED_FLAT in flags


def test_dynamic_ignored_for_gas() -> None:
    boiler = Generator.for_kind(
        "boiler", "CV", GeneratorKind.GAS_BOILER, price_mode=PriceMode.DYNAMIC
    )
    energy = _energy(carrier=2.0, heat_total=16.0, heat_dhw=2.0, heat_space=14.0)
    cost, flags = generator_cost(
        boiler,
        energy,
        daily_price=1.10,
        hourly_electric={0: 2.0},
        hourly_price={0: 9.99},
    )
    assert cost == pytest.approx(2.2)
    assert flags == set()


def test_pipeline_flat_and_dynamic_and_space_share() -> None:
    site = Site(
        id="home",
        generators=[
            Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER),
            Generator.for_kind(
                "hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE, price_mode=PriceMode.DYNAMIC
            ),
        ],
    )
    day = START
    weather = {day: DailyWeather(day, 2.0, 3.0, 100.0)}
    gas = {day: (4.0, set())}
    hp_electric = {day: (6.0, set())}
    records = build_daily_records(
        site,
        weather,
        {"boiler": gas, "hp": hp_electric},
        baselines={"boiler": 0.5, "hp": None},
        prices={"boiler": 1.30, "hp": 0.20},
        hourly_electric_by_generator={"hp": {day: {8: 2.0, 18: 4.0}}},
        hourly_price_by_generator={"hp": {day: {8: 0.05, 18: 0.40}}},
    )
    record = records[0]
    assert record.cost_eur == pytest.approx(4.0 * 1.30 + 2.0 * 0.05 + 4.0 * 0.40)
    assert Flag.PRICE_ESTIMATED_FLAT not in record.flags
    boiler = record.heat_by_generator["boiler"]
    hp = record.heat_by_generator["hp"]
    assert boiler.cost_eur == pytest.approx(5.2)
    assert hp.cost_eur == pytest.approx(1.70)
    expected_space = space_share_of_cost(boiler, boiler.cost_eur) + space_share_of_cost(
        hp, hp.cost_eur
    )
    assert record.cost_space_eur == pytest.approx(expected_space)
    assert record.co2_kg == pytest.approx(4.0 * 1.78 + 6.0 * 0.30)


def test_pipeline_dynamic_fallback_flag() -> None:
    site = Site(
        id="home",
        generators=[
            Generator.for_kind(
                "hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE, price_mode=PriceMode.DYNAMIC
            )
        ],
    )
    day = START
    weather = {day: DailyWeather(day, 1.0, 2.0)}
    records = build_daily_records(
        site,
        weather,
        {"hp": {day: (5.0, set())}},
        baselines={"hp": None},
        prices={"hp": 0.22},
    )
    assert records[0].cost_eur == pytest.approx(5.0 * 0.22)
    assert Flag.PRICE_ESTIMATED_FLAT in records[0].flags
    assert records[0].heat_by_generator["hp"].cost_eur == pytest.approx(1.10)


def test_allocate_period_uses_cost_space_not_total() -> None:
    living = Room(
        id="living",
        name="Living",
        demand_entity="sensor.living",
        rated_output_w=1000.0,
    )
    site = DailyRecord(
        date=START,
        site_id="home",
        heat_space_kwh=20.0,
        heat_dhw_kwh=5.0,
        cost_eur=10.0,
        cost_space_eur=8.0,
    )
    records, _unallocated = allocate_period(
        [living],
        {START: {"living": RoomDayInput(raw=100.0)}},
        [site],
    )
    assert records[0].cost_room_eur == pytest.approx(8.0)


def test_metered_room_uses_own_price_or_site_default() -> None:
    plug = Room(
        id="garage",
        name="Garage",
        demand_entity="sensor.garage",
        demand_kind=DemandKind.METERED_ENERGY,
    )
    living = Room(
        id="living",
        name="Living",
        demand_entity="sensor.living",
        rated_output_w=1000.0,
    )
    result = allocate_day(
        [plug, living],
        {"garage": RoomDayInput(raw=4.0), "living": RoomDayInput(raw=100.0)},
        heat_space_kwh=24.0,
        cost_space_eur=12.0,
        metered_prices={"garage": 0.50},
        day=START,
    )
    by_id = {record.room_id: record for record in result.records}
    assert by_id["garage"].cost_room_eur == pytest.approx(2.0)
    assert by_id["living"].cost_room_eur == pytest.approx(10.0)


def test_metered_room_falls_back_to_site_default_price() -> None:
    plug = Room(
        id="garage",
        name="Garage",
        demand_entity="sensor.garage",
        demand_kind=DemandKind.METERED_ENERGY,
    )
    living = Room(
        id="living",
        name="Living",
        demand_entity="sensor.living",
        rated_output_w=1000.0,
    )
    result = allocate_day(
        [plug, living],
        {"garage": RoomDayInput(raw=4.0), "living": RoomDayInput(raw=100.0)},
        heat_space_kwh=24.0,
        cost_space_eur=12.0,
        day=START,
    )
    by_id = {record.room_id: record for record in result.records}
    assert by_id["garage"].cost_room_eur == pytest.approx(2.0)
    assert by_id["living"].cost_room_eur == pytest.approx(10.0)


def test_site_default_price() -> None:
    assert site_default_price(8.0, 20.0) == pytest.approx(0.40)
    assert site_default_price(None, 20.0) is None
    assert site_default_price(8.0, 0.0) is None


def test_hourly_alignment_uses_shared_keys() -> None:
    """Hour keys are opaque (timestamps in the HA layer); only intersection counts."""
    electric = {1_700_000_000: 1.0, 1_700_003_600: 2.0, 1_700_007_200: 3.0}
    price = {1_700_000_000: 0.10, 1_700_003_600: 0.50}
    assert hourly_cost(electric, price) == pytest.approx(1.0 * 0.10 + 2.0 * 0.50)
