"""Cost and CO₂ (METHODS §13) including dynamic hourly tariffs (ADR 0006)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from heatprint_core.cost import (
    ELECTRIC_KINDS,
    avg_price_paid,
    billed_amount,
    generator_cost,
    group_hourly_by_local_day,
    hourly_cost,
    mean_of,
    site_default_price,
    space_share_of_cost,
)
from heatprint_core.flags import EXCLUSION_FLAGS, Flag, is_usable
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
AMSTERDAM = ZoneInfo("Europe/Amsterdam")


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


def test_billed_amount_electric_kinds_use_electric_kwh() -> None:
    energy = _energy(carrier=9.0, electric=3.0)
    for kind in ELECTRIC_KINDS:
        generator = Generator.for_kind("g", "G", kind, role=Role.SPACE)
        assert billed_amount(generator, energy) == 3.0
    boiler = Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)
    assert billed_amount(boiler, energy) == 9.0


def test_no_price_means_no_cost_but_co2_still_computed() -> None:
    site = Site(
        id="home",
        generators=[Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)],
    )
    day = START
    records = build_daily_records(
        site,
        {day: DailyWeather(day, 2.0)},
        {"boiler": {day: (3.0, set())}},
        baselines={"boiler": None},
    )
    assert records[0].cost_eur is None
    assert records[0].cost_space_eur is None
    assert records[0].co2_kg == pytest.approx(3.0 * 1.78)


def test_per_day_price_entity_series() -> None:
    """Coordinator passes price_entity daily means as ``{date: price}``."""
    site = Site(
        id="home",
        generators=[Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)],
    )
    day_a = START
    day_b = START + timedelta(days=1)
    weather = {day_a: DailyWeather(day_a, 1.0), day_b: DailyWeather(day_b, 2.0)}
    records = build_daily_records(
        site,
        weather,
        {"boiler": {day_a: (2.0, set()), day_b: (2.0, set())}},
        baselines={"boiler": None},
        prices={"boiler": {day_a: 1.10, day_b: 1.40}},
    )
    by_date = {record.date: record for record in records}
    assert by_date[day_a].cost_eur == pytest.approx(2.2)
    assert by_date[day_b].cost_eur == pytest.approx(2.8)


def test_live_co2_entity_overrides_electric_days() -> None:
    """``co2_entity`` daily means land here as a per-day factor map (METHODS 13.3)."""
    hp = Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE)
    site = Site(id="home", generators=[hp])
    day_live = START
    day_fallback = START + timedelta(days=1)
    weather = {
        day_live: DailyWeather(day_live, 1.0),
        day_fallback: DailyWeather(day_fallback, 2.0),
    }
    records = build_daily_records(
        site,
        weather,
        {"hp": {day_live: (4.0, set()), day_fallback: (4.0, set())}},
        baselines={"hp": None},
        co2_factors={"hp": {day_live: 0.12}},
    )
    by_date = {record.date: record for record in records}
    assert by_date[day_live].co2_kg == pytest.approx(4.0 * 0.12)
    assert by_date[day_fallback].co2_kg == pytest.approx(4.0 * 0.30)


def test_price_estimated_flat_is_usable() -> None:
    assert Flag.PRICE_ESTIMATED_FLAT not in EXCLUSION_FLAGS
    assert is_usable({Flag.PRICE_ESTIMATED_FLAT})


def test_avg_price_paid() -> None:
    assert avg_price_paid(1.70, 6.0) == pytest.approx(1.70 / 6.0)
    assert avg_price_paid(None, 6.0) is None
    assert avg_price_paid(1.70, 0.0) is None


def test_pipeline_avg_price_paid_from_hourly_series() -> None:
    site = Site(
        id="home",
        generators=[
            Generator.for_kind(
                "hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE, price_mode=PriceMode.DYNAMIC
            )
        ],
    )
    day = START
    records = build_daily_records(
        site,
        {day: DailyWeather(day, 1.0)},
        {"hp": {day: (6.0, set())}},
        baselines={"hp": None},
        prices={"hp": 0.20},
        hourly_electric_by_generator={"hp": {day: {8: 2.0, 18: 4.0}}},
        hourly_price_by_generator={"hp": {day: {8: 0.05, 18: 0.40}}},
    )
    energy = records[0].heat_by_generator["hp"]
    assert avg_price_paid(energy.cost_eur, energy.electric_kwh or 0.0) == pytest.approx(
        (2.0 * 0.05 + 4.0 * 0.40) / 6.0
    )


def test_allocate_period_falls_back_to_total_times_space_share() -> None:
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
    )
    records, _unallocated = allocate_period(
        [living],
        {START: {"living": RoomDayInput(raw=100.0)}},
        [site],
    )
    assert records[0].cost_room_eur == pytest.approx(8.0)


def test_allocate_day_without_site_cost_leaves_room_cost_none() -> None:
    living = Room(
        id="living",
        name="Living",
        demand_entity="sensor.living",
        rated_output_w=1000.0,
    )
    result = allocate_day(
        [living],
        {"living": RoomDayInput(raw=100.0)},
        heat_space_kwh=10.0,
        day=START,
    )
    assert result.records[0].cost_room_eur is None


def _hourly_samples_for_local_day(day: date) -> list[tuple[float, float]]:
    """One sample per UTC hour whose local date is ``day`` (DST-safe)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=AMSTERDAM).astimezone(UTC)
    end = datetime.combine(
        day + timedelta(days=1), datetime.min.time(), tzinfo=AMSTERDAM
    ).astimezone(UTC)
    samples: list[tuple[float, float]] = []
    cursor = start
    while cursor < end:
        samples.append((cursor.timestamp(), 1.0))
        cursor += timedelta(hours=1)
    return samples


def test_group_hourly_by_local_day_dst_amsterdam() -> None:
    """Spring-forward has 23 hours; fall-back has 25 (METHODS 13.2)."""
    spring = date(2026, 3, 29)
    autumn = date(2026, 10, 25)
    grouped_spring = group_hourly_by_local_day(_hourly_samples_for_local_day(spring), AMSTERDAM)
    grouped_autumn = group_hourly_by_local_day(_hourly_samples_for_local_day(autumn), AMSTERDAM)
    assert list(grouped_spring) == [spring]
    assert list(grouped_autumn) == [autumn]
    assert len(grouped_spring[spring]) == 23
    assert len(grouped_autumn[autumn]) == 25


def test_live_co2_entity_does_not_override_gas() -> None:
    """``co2_entity`` is kg/kWh and only applied to electric generators (METHODS 13.3)."""
    site = Site(
        id="home",
        generators=[
            Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER),
            Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE),
        ],
    )
    day = START
    records = build_daily_records(
        site,
        {day: DailyWeather(day, 1.0)},
        {"boiler": {day: (2.0, set())}, "hp": {day: (4.0, set())}},
        baselines={"boiler": None, "hp": None},
        co2_factors={"hp": {day: 0.12}},
    )
    assert records[0].co2_kg == pytest.approx(2.0 * 1.78 + 4.0 * 0.12)


def test_site_co2_factor_override() -> None:
    """Site pricing options arrive as a constant per generator (METHODS 13.3)."""
    site = Site(
        id="home",
        generators=[Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)],
    )
    day = START
    records = build_daily_records(
        site,
        {day: DailyWeather(day, 1.0)},
        {"boiler": {day: (3.0, set())}},
        baselines={"boiler": None},
        co2_factors={"boiler": 2.05},
    )
    assert records[0].co2_kg == pytest.approx(3.0 * 2.05)


def test_partial_hourly_intersection_does_not_flag() -> None:
    """A shared hour is enough; unmatched hours are skipped without fallback (METHODS 13.2)."""
    hp = Generator.for_kind(
        "hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE, price_mode=PriceMode.DYNAMIC
    )
    energy = _energy(electric=6.0, heat_total=21.0, heat_dhw=0.0, heat_space=21.0)
    cost, flags = generator_cost(
        hp,
        energy,
        daily_price=0.99,
        hourly_electric={8: 2.0, 12: 1.0, 18: 3.0},
        hourly_price={8: 0.10, 18: 0.40},
    )
    assert cost == pytest.approx(2.0 * 0.10 + 3.0 * 0.40)
    assert Flag.PRICE_ESTIMATED_FLAT not in flags


def test_billed_amount_district_uses_carrier() -> None:
    energy = _energy(carrier=1.5, electric=9.0)
    district = Generator.for_kind("dh", "STAD", GeneratorKind.DISTRICT_HEAT)
    assert billed_amount(district, energy) == 1.5


def test_space_share_of_cost_zero_total() -> None:
    space_only = _energy(heat_total=0.0, heat_dhw=0.0, heat_space=1.0)
    none = _energy(heat_total=0.0, heat_dhw=0.0, heat_space=0.0)
    assert space_share_of_cost(space_only, 4.0) == pytest.approx(4.0)
    assert space_share_of_cost(none, 4.0) == 0.0
    assert space_share_of_cost(none, None) is None


def test_missing_price_day_leaves_that_day_uncosted() -> None:
    site = Site(
        id="home",
        generators=[Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)],
    )
    day_priced = START
    day_gap = START + timedelta(days=1)
    weather = {
        day_priced: DailyWeather(day_priced, 1.0),
        day_gap: DailyWeather(day_gap, 2.0),
    }
    records = build_daily_records(
        site,
        weather,
        {"boiler": {day_priced: (2.0, set()), day_gap: (2.0, set())}},
        baselines={"boiler": None},
        prices={"boiler": {day_priced: 1.10}},
    )
    by_date = {record.date: record for record in records}
    assert by_date[day_priced].cost_eur == pytest.approx(2.2)
    assert by_date[day_gap].cost_eur is None
    assert by_date[day_gap].co2_kg == pytest.approx(2.0 * 1.78)
