"""Rooms: demand integral, weights, allocation and room signature (METHODS §12)."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from heatprint_core.constants import DEFAULT_CEILING_HEIGHT_M, DEFAULT_OUTPUT_W_PER_M2
from heatprint_core.flags import Flag
from heatprint_core.models import (
    DailyRecord,
    DemandKind,
    EmitterKind,
    Period,
    Room,
    Site,
)
from heatprint_core.rooms import (
    RoomDayInput,
    allocate_day,
    allocate_period,
    apply_room_not_fitted,
    daily_demand_integral,
    fit_room_signature,
    indicative_ua_w_per_k,
    room_weight,
)
from tests.conftest import synthetic_records, synthetic_weather


def test_demand_integral_percentage_and_valve() -> None:
    assert daily_demand_integral(DemandKind.PERCENTAGE, 50.0) == pytest.approx(0.5)
    assert daily_demand_integral(DemandKind.VALVE_POSITION, 100.0) == pytest.approx(1.0)
    assert daily_demand_integral(DemandKind.PERCENTAGE, 0.0) == 0.0
    assert daily_demand_integral(DemandKind.PERCENTAGE, None) is None
    assert daily_demand_integral(DemandKind.PERCENTAGE, 250.0) == 1.0


def test_demand_integral_binary_and_metered() -> None:
    assert daily_demand_integral(DemandKind.BINARY, 0.25) == pytest.approx(0.25)
    assert daily_demand_integral(DemandKind.BINARY, 12.0, heating_hours=12.0) == pytest.approx(0.5)
    assert daily_demand_integral(DemandKind.BINARY, 6.0) == pytest.approx(0.25)  # hours-on
    assert daily_demand_integral(DemandKind.METERED_ENERGY, 4.2) == pytest.approx(4.2)
    assert daily_demand_integral(DemandKind.METERED_ENERGY, -1.0) == 0.0


def test_room_weight_rated_area_and_assumed() -> None:
    rated = Room(id="a", name="A", rated_output_w=1200.0, floor_area_m2=20.0)
    assert room_weight(rated) == (1200.0, False)
    area = Room(id="b", name="B", emitter_kind=EmitterKind.UNDERFLOOR, floor_area_m2=10.0)
    weight, assumed = room_weight(area)
    assert assumed is True
    assert weight == pytest.approx(10.0 * DEFAULT_OUTPUT_W_PER_M2["underfloor"])
    unit = Room(id="c", name="C")
    assert room_weight(unit) == (1.0, True)


def test_room_volume_is_captured_not_used() -> None:
    room = Room(id="d", name="D", floor_area_m2=12.0)
    assert room.resolved_volume_m3 == pytest.approx(12.0 * DEFAULT_CEILING_HEIGHT_M)
    explicit = Room(id="e", name="E", floor_area_m2=12.0, volume_m3=40.0)
    assert explicit.resolved_volume_m3 == 40.0


def test_allocate_day_weighted_shares_and_unallocated() -> None:
    living = Room(
        id="living",
        name="Living",
        demand_entity="sensor.living",
        rated_output_w=2000.0,
        floor_area_m2=30.0,
    )
    bath = Room(
        id="bath",
        name="Bath",
        demand_entity="sensor.bath",
        rated_output_w=500.0,
        floor_area_m2=6.0,
    )
    unused = Room(id="unused", name="Unused")  # no demand entity
    result = allocate_day(
        [living, bath, unused],
        {
            "living": RoomDayInput(raw=50.0, t_room_mean=20.0),
            "bath": RoomDayInput(raw=100.0, t_room_mean=21.0),
        },
        heat_space_kwh=30.0,
        day=date(2026, 1, 10),
        cost_space_eur=6.0,
    )
    by_id = {record.room_id: record for record in result.records}
    # w*D: living 2000*0.5=1000, bath 500*1=500 → shares 2/3 and 1/3
    assert by_id["living"].share == pytest.approx(2 / 3)
    assert by_id["bath"].share == pytest.approx(1 / 3)
    assert by_id["living"].heat_room_kwh == pytest.approx(20.0)
    assert by_id["bath"].heat_room_kwh == pytest.approx(10.0)
    assert by_id["living"].cost_room_eur == pytest.approx(4.0)
    assert by_id["bath"].cost_room_eur == pytest.approx(2.0)
    assert by_id["living"].heat_kwh_per_m2 == pytest.approx(20.0 / 30.0)
    assert result.heat_unallocated_kwh == pytest.approx(0.0)
    assert Flag.ROOM_DEMAND_MISSING in by_id["unused"].flags
    assert by_id["unused"].heat_room_kwh is None


def test_allocate_day_metered_bypass_and_missing() -> None:
    plug = Room(
        id="garage",
        name="Garage",
        demand_entity="sensor.garage_kwh",
        demand_kind=DemandKind.METERED_ENERGY,
        emitter_kind=EmitterKind.ELECTRIC,
    )
    living = Room(
        id="living",
        name="Living",
        demand_entity="sensor.living",
        rated_output_w=1000.0,
    )
    missing = Room(
        id="office",
        name="Office",
        demand_entity="sensor.office",
        rated_output_w=1000.0,
    )
    result = allocate_day(
        [plug, living, missing],
        {
            "garage": RoomDayInput(raw=4.0),
            "living": RoomDayInput(raw=80.0, from_history=True),
        },
        heat_space_kwh=24.0,
        day=date(2026, 1, 11),
    )
    by_id = {record.room_id: record for record in result.records}
    assert by_id["garage"].heat_room_kwh == pytest.approx(4.0)
    assert by_id["living"].heat_room_kwh == pytest.approx(20.0)
    assert by_id["office"].heat_room_kwh is None
    assert Flag.ROOM_DEMAND_MISSING in by_id["office"].flags
    assert Flag.ROOM_DEMAND_FROM_HISTORY in by_id["living"].flags
    assert result.heat_unallocated_kwh == pytest.approx(0.0)


def test_allocate_day_all_missing_is_fully_unallocated() -> None:
    room = Room(id="living", name="Living", demand_entity="sensor.living")
    result = allocate_day([room], {}, heat_space_kwh=12.0, day=date(2026, 1, 12))
    assert result.heat_unallocated_kwh == pytest.approx(12.0)
    assert result.records[0].heat_room_kwh is None


def test_allocate_day_disabled_room_is_skipped() -> None:
    off = Room(id="off", name="Off", demand_entity="sensor.off", enabled=False)
    on = Room(id="on", name="On", demand_entity="sensor.on", rated_output_w=1.0)
    result = allocate_day(
        [off, on],
        {"off": RoomDayInput(raw=100.0), "on": RoomDayInput(raw=100.0)},
        heat_space_kwh=10.0,
        day=date(2026, 1, 13),
    )
    assert [record.room_id for record in result.records] == ["on"]
    assert result.records[0].heat_room_kwh == pytest.approx(10.0)


def test_weight_assumed_flag_on_floor_area_default() -> None:
    room = Room(
        id="bed",
        name="Bed",
        demand_entity="sensor.bed",
        floor_area_m2=12.0,
        emitter_kind=EmitterKind.RADIATOR,
    )
    result = allocate_day(
        [room],
        {"bed": RoomDayInput(raw=40.0)},
        heat_space_kwh=8.0,
        day=date(2026, 1, 14),
    )
    assert Flag.ROOM_WEIGHT_ASSUMED in result.records[0].flags
    assert result.records[0].heat_room_kwh == pytest.approx(8.0)


def test_indicative_ua() -> None:
    # 4.8 kWh over 8 h with 10 K delta → 4.8 / 10 / 8 * 1000 = 60 W/K
    assert indicative_ua_w_per_k(4.8, 20.0, 10.0, 8.0) == pytest.approx(60.0)
    assert indicative_ua_w_per_k(4.8, 10.0, 20.0, 8.0) is None
    assert indicative_ua_w_per_k(4.8, 20.0, 10.0, 0.0) is None


def test_site_json_round_trip_includes_rooms() -> None:
    site = Site(
        id="home",
        rooms=[
            Room(
                id="living",
                name="Living",
                demand_entity="sensor.living_verwarming",
                demand_kind=DemandKind.PERCENTAGE,
                emitter_kind=EmitterKind.UNDERFLOOR,
                floor_area_m2=28.0,
            )
        ],
    )
    restored = Site.from_dict(site.to_dict())
    assert restored == site
    assert restored.room("living").emitter_kind is EmitterKind.UNDERFLOOR


def test_allocate_period_reconciles_against_site() -> None:
    rooms = [
        Room(id="a", name="A", demand_entity="s.a", rated_output_w=1000.0),
        Room(id="b", name="B", demand_entity="s.b", rated_output_w=1000.0),
    ]
    site_records = [
        DailyRecord(date=date(2026, 1, 1), site_id="home", heat_space_kwh=20.0, t_mean=2.0),
        DailyRecord(date=date(2026, 1, 2), site_id="home", heat_space_kwh=10.0, t_mean=5.0),
    ]
    inputs = {
        date(2026, 1, 1): {
            "a": RoomDayInput(raw=100.0),
            "b": RoomDayInput(raw=100.0),
        },
        date(2026, 1, 2): {"a": RoomDayInput(raw=50.0)},
    }
    records, unallocated = allocate_period(rooms, inputs, site_records)
    by_day: dict[date, float] = {}
    for record in records:
        if record.heat_room_kwh is None:
            continue
        by_day[record.date] = by_day.get(record.date, 0.0) + record.heat_room_kwh
    assert by_day[date(2026, 1, 1)] + unallocated[date(2026, 1, 1)] == pytest.approx(20.0)
    assert by_day[date(2026, 1, 2)] + unallocated[date(2026, 1, 2)] == pytest.approx(10.0)
    assert unallocated[date(2026, 1, 2)] == pytest.approx(0.0)


def _synthetic_multi_room_house(n_days: int = 150) -> dict[str, object]:
    """METHODS §12.8: known UA_r, demand ~ deficit, site heat = sum of room heats."""
    rng = random.Random(12)
    start = date(2024, 10, 1)
    weather = synthetic_weather(start, n_days, rng)
    specs = (
        ("living", 3.0, 16.0, 2000.0),  # slope_b kWh/K·day, T_b, rated W
        ("office", 1.2, 15.0, 800.0),
        ("bath", 0.6, 18.0, 400.0),
    )
    site_records = synthetic_records(weather, 0.0, 1.0, 16.0, 0.0, 0.0, rng)
    rooms: list[Room] = []
    room_inputs: dict[date, dict[str, RoomDayInput]] = {}
    true_heat: dict[str, dict[date, float]] = {room_id: {} for room_id, *_ in specs}
    for index, record in enumerate(site_records):
        tac = record.tac_house if record.tac_house is not None else record.t_mean or 10.0
        heats: list[float] = []
        day_inputs: dict[str, RoomDayInput] = {}
        for room_id, slope, tb, rated in specs:
            deficit = max(0.0, tb - tac)
            heat = slope * deficit + rng.gauss(0, 0.15)
            heat = max(0.0, heat)
            heats.append(heat)
            true_heat[room_id][record.date] = heat
            # Demand roughly proportional to that room's own deficit (+ noise).
            demand_pct = min(100.0, max(0.0, 8.0 * deficit + rng.gauss(0, 3.0)))
            day_inputs[room_id] = RoomDayInput(raw=demand_pct, t_room_mean=20.0)
            if index == 0:
                rooms.append(
                    Room(
                        id=room_id,
                        name=room_id.title(),
                        demand_entity=f"sensor.{room_id}",
                        rated_output_w=rated,
                    )
                )
        record.heat_space_kwh = sum(heats)
        room_inputs[record.date] = day_inputs
    return {
        "rooms": rooms,
        "site_records": site_records,
        "inputs": room_inputs,
        "true_heat": true_heat,
        "specs": specs,
        "period": Period(start, start + timedelta(days=n_days - 1), "2024/25"),
    }


def test_synthetic_house_shares_sum_to_site() -> None:
    house = _synthetic_multi_room_house()
    records, unallocated = allocate_period(house["rooms"], house["inputs"], house["site_records"])
    by_day: dict[date, float] = {}
    for record in records:
        if record.heat_room_kwh is None:
            continue
        by_day[record.date] = by_day.get(record.date, 0.0) + record.heat_room_kwh
    for site in house["site_records"]:
        total = by_day.get(site.date, 0.0) + unallocated[site.date]
        assert total == pytest.approx(site.heat_space_kwh, abs=1e-9)
        assert unallocated[site.date] == pytest.approx(0.0, abs=1e-9)


def test_synthetic_house_fit_recovers_ua_within_20_percent() -> None:
    """METHODS §12.8: room fit recovers UA_r within 20% (looser than the site 5%)."""
    house = _synthetic_multi_room_house()
    records, _unallocated = allocate_period(house["rooms"], house["inputs"], house["site_records"])
    by_room: dict[str, list] = {}
    for record in records:
        by_room.setdefault(record.room_id, []).append(record)
    rooms = {room.id: room for room in house["rooms"]}
    specs = {room_id: (slope, tb) for room_id, slope, tb, _rated in house["specs"]}
    for room_id, room_records in by_room.items():
        fit = fit_room_signature(
            rooms[room_id],
            room_records,
            house["site_records"],
            house["period"],
            min_days=30,
        )
        assert fit is not None, room_id
        true_slope, true_tb = specs[room_id]
        true_ua = true_slope * 1000 / 24
        assert abs(fit.ua_w_per_k - true_ua) / true_ua < 0.20, (
            room_id,
            fit.ua_w_per_k,
            true_ua,
        )
        assert abs(fit.balance_temp - true_tb) < 2.5, (room_id, fit.balance_temp, true_tb)
        assert fit.n_days >= 30
        assert fit.room_id == room_id


def test_room_fit_none_before_thirty_days() -> None:
    room = Room(id="tiny", name="Tiny", demand_entity="sensor.tiny", rated_output_w=500.0)
    site_records = [
        DailyRecord(
            date=date(2026, 1, 1) + timedelta(days=i),
            site_id="home",
            tac_house=5.0,
            heat_space_kwh=10.0,
            t_mean=4.0,
        )
        for i in range(20)
    ]
    from heatprint_core.models import DailyRoomRecord

    room_records = [
        DailyRoomRecord(
            date=record.date,
            room_id="tiny",
            demand_integral=0.5,
            heat_room_kwh=5.0,
            share=0.5,
        )
        for record in site_records
    ]
    fit = fit_room_signature(
        room,
        room_records,
        site_records,
        Period(site_records[0].date, site_records[-1].date),
        min_days=30,
    )
    assert fit is None
    assert all(Flag.ROOM_NOT_FITTED in record.flags for record in room_records)


def _short_room_series(n_days: int, room_id: str = "tiny"):
    site_records = [
        DailyRecord(
            date=date(2026, 1, 1) + timedelta(days=i),
            site_id="home",
            tac_house=5.0,
            heat_space_kwh=10.0,
            t_mean=4.0,
        )
        for i in range(n_days)
    ]
    from heatprint_core.models import DailyRoomRecord

    room_records = [
        DailyRoomRecord(
            date=record.date,
            room_id=room_id,
            demand_integral=0.5,
            heat_room_kwh=5.0,
            share=0.5,
        )
        for record in site_records
    ]
    return site_records, room_records


def test_apply_room_not_fitted_when_below_min_days() -> None:
    site_records, room_records = _short_room_series(10)
    flagged = apply_room_not_fitted(room_records, site_records, min_days=30)
    assert flagged == {"tiny"}
    assert Flag.ROOM_NOT_FITTED in room_records[0].flags
    assert Flag.ROOM_NOT_FITTED in room_records[-1].flags


def test_apply_room_not_fitted_skips_already_fitted_rooms() -> None:
    site_records, room_records = _short_room_series(10)
    flagged = apply_room_not_fitted(room_records, site_records, min_days=30, skip_room_ids={"tiny"})
    assert flagged == set()
    assert Flag.ROOM_NOT_FITTED not in room_records[0].flags


def test_apply_room_not_fitted_not_emitted_with_enough_days() -> None:
    site_records, room_records = _short_room_series(40)
    flagged = apply_room_not_fitted(room_records, site_records, min_days=30)
    assert flagged == set()
    assert Flag.ROOM_NOT_FITTED not in room_records[0].flags
