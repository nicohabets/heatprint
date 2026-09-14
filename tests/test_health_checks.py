"""METHODS §14 data-source health checks (stuck, implausible, scale, stalled)."""

from __future__ import annotations

from datetime import date, timedelta

from heatprint_core.flags import Flag
from heatprint_core.health import (
    HINTS,
    HealthCheckConfig,
    HealthCheckName,
    HealthFinding,
    HealthSourceKind,
    WeatherSourceRef,
    findings_as_attributes,
    run_health_checks,
    stale_health_issue_ids,
)
from heatprint_core.models import (
    DailyEnergy,
    DailyRecord,
    DailyRoomRecord,
    DemandKind,
    Generator,
    GeneratorKind,
    Provider,
    Room,
    Site,
    WeatherSourceConfig,
)

AS_OF = date(2026, 2, 15)


def _energy(day: date, generator_id: str, carrier: float, heat: float | None = None) -> DailyEnergy:
    space = carrier if heat is None else heat
    return DailyEnergy(
        date=day,
        generator_id=generator_id,
        carrier_amount=carrier,
        electric_kwh=None,
        heat_total_kwh=space,
        heat_dhw_kwh=0.0,
        heat_space_kwh=space,
    )


def _record(
    day: date,
    *,
    boiler: float | None = 5.0,
    hp: float | None = 10.0,
    dd: float = 12.0,
    provisional: bool = False,
    flags: set[Flag] | None = None,
) -> DailyRecord:
    gens: dict[str, DailyEnergy] = {}
    if boiler is not None:
        gens["boiler"] = _energy(day, "boiler", boiler)
    if hp is not None:
        gens["hp"] = _energy(day, "hp", hp)
    record_flags = set(flags or [])
    if provisional:
        record_flags.add(Flag.WEATHER_PROVISIONAL)
    return DailyRecord(
        date=day,
        site_id="home",
        dd={"classic": dd, "knmi14": dd, "pbl": dd, "house": dd},
        heat_space_kwh=sum(item.heat_space_kwh for item in gens.values()),
        heat_by_generator=gens,
        flags=record_flags,
    )


def _series(
    days: int,
    *,
    as_of: date = AS_OF,
    boiler: float | None = 5.0,
    hp: float | None = 10.0,
    dd: float = 12.0,
    last_boiler: float | None = None,
    last_hp: float | None = None,
    last_dd: float | None = None,
    stuck_boiler_days: int = 0,
    provisional_days: int = 0,
    boiler_recent: float | None = None,
    boiler_older: float | None = None,
    scale_window: int = 15,
) -> list[DailyRecord]:
    """Build ``days`` records ending at ``as_of`` (inclusive)."""
    records: list[DailyRecord] = []
    start = as_of - timedelta(days=days - 1)
    for offset in range(days):
        day = start + timedelta(days=offset)
        from_end = (as_of - day).days
        day_boiler = boiler
        day_hp = hp
        day_dd = dd
        if boiler_recent is not None and boiler_older is not None:
            day_boiler = boiler_recent if from_end < scale_window else boiler_older
        if last_boiler is not None and day == as_of:
            day_boiler = last_boiler
        if last_hp is not None and day == as_of:
            day_hp = last_hp
        if last_dd is not None and day == as_of:
            day_dd = last_dd
        if stuck_boiler_days and from_end < stuck_boiler_days:
            day_boiler = 0.0
        records.append(
            _record(
                day,
                boiler=day_boiler,
                hp=day_hp,
                dd=day_dd,
                provisional=from_end < provisional_days,
            )
        )
    return records


def _site() -> Site:
    return Site(
        id="home",
        name="Thuis",
        weather=WeatherSourceConfig(provider=Provider.KNMI, station_id="380"),
        generators=[
            Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER),
            Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP),
        ],
        rooms=[
            Room(id="living", name="Woonkamer", demand_kind=DemandKind.METERED_ENERGY),
            Room(id="bath", name="Badkamer", demand_kind=DemandKind.PERCENTAGE),
        ],
    )


def _room_days(
    room_id: str,
    days: int,
    value: float,
    *,
    as_of: date = AS_OF,
    last: float | None = None,
    stuck_days: int = 0,
    recent: float | None = None,
    older: float | None = None,
    scale_window: int = 15,
) -> list[DailyRoomRecord]:
    start = as_of - timedelta(days=days - 1)
    records: list[DailyRoomRecord] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        from_end = (as_of - day).days
        amount = value
        if recent is not None and older is not None:
            amount = recent if from_end < scale_window else older
        if last is not None and day == as_of:
            amount = last
        if stuck_days and from_end < stuck_days:
            amount = 0.0
        records.append(
            DailyRoomRecord(
                date=day,
                room_id=room_id,
                demand_integral=amount,
                heat_room_kwh=amount,
            )
        )
    return records


def _names(findings: list[HealthFinding]) -> set[tuple[str, str, str]]:
    return {(item.check.value, item.source_kind.value, item.source_id) for item in findings}


def test_healthy_hybrid_series_opens_nothing() -> None:
    findings = run_health_checks(_series(40), site=_site(), as_of=AS_OF, primary_method="pbl")
    assert findings == []


def test_stuck_gas_meter_while_heat_pump_heats() -> None:
    """STUCK_VALUE: boiler increment is 0 for 3 days; HP still delivers space heat."""
    records = _series(20, stuck_boiler_days=3)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert _names(findings) == {
        (HealthCheckName.STUCK_VALUE.value, HealthSourceKind.GENERATOR.value, "boiler")
    }
    stuck = findings[0]
    assert stuck.source_name == "CV"
    assert stuck.hint == HINTS[HealthCheckName.STUCK_VALUE]
    assert "polling" in stuck.hint


def test_stuck_does_not_fire_without_site_heating() -> None:
    records = _series(10, boiler=0.0, hp=0.0, stuck_boiler_days=3)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert HealthCheckName.STUCK_VALUE not in {item.check for item in findings}


def test_stuck_is_not_a_data_gap() -> None:
    """Missing generator-days are ENERGY_MISSING, not an unchanging meter."""
    records = _series(10)
    for record in records[-3:]:
        record.heat_by_generator.pop("boiler")
        record.heat_space_kwh = record.heat_by_generator["hp"].heat_space_kwh
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert HealthCheckName.STUCK_VALUE not in {item.check for item in findings}


def test_stuck_metered_room() -> None:
    records = _series(10)
    rooms = _room_days("living", 10, 8.0, stuck_days=3)
    findings = run_health_checks(records, site=_site(), room_records=rooms, as_of=AS_OF)
    assert (
        HealthCheckName.STUCK_VALUE.value,
        HealthSourceKind.ROOM.value,
        "living",
    ) in _names(findings)


def test_percentage_room_idle_is_not_stuck() -> None:
    records = _series(10)
    rooms = _room_days("bath", 10, 0.4, stuck_days=3)
    findings = run_health_checks(records, site=_site(), room_records=rooms, as_of=AS_OF)
    assert (
        HealthCheckName.STUCK_VALUE.value,
        HealthSourceKind.ROOM.value,
        "bath",
    ) not in _names(findings)


def test_implausible_generator_heat() -> None:
    records = _series(40, last_boiler=80.0)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert (
        HealthCheckName.IMPLAUSIBLE_VALUE.value,
        HealthSourceKind.GENERATOR.value,
        "boiler",
    ) in _names(findings)
    hit = next(item for item in findings if item.check is HealthCheckName.IMPLAUSIBLE_VALUE)
    assert hit.value == 80.0
    assert hit.typical == 5.0


def test_implausible_degree_days_names_weather_source() -> None:
    records = _series(40, last_dd=80.0)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF, primary_method="pbl")
    assert (
        HealthCheckName.IMPLAUSIBLE_VALUE.value,
        HealthSourceKind.WEATHER.value,
        "knmi_380",
    ) in _names(findings)
    hit = next(
        item
        for item in findings
        if item.check is HealthCheckName.IMPLAUSIBLE_VALUE
        and item.source_kind is HealthSourceKind.WEATHER
    )
    assert "Maastricht" in hit.source_name
    assert hit.series == "dd_pbl"


def test_implausible_room_demand() -> None:
    records = _series(40)
    rooms = _room_days("living", 40, 4.0, last=40.0)
    findings = run_health_checks(records, site=_site(), room_records=rooms, as_of=AS_OF)
    assert (
        HealthCheckName.IMPLAUSIBLE_VALUE.value,
        HealthSourceKind.ROOM.value,
        "living",
    ) in _names(findings)


def test_implausible_needs_history() -> None:
    records = _series(5, last_boiler=80.0)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert HealthCheckName.IMPLAUSIBLE_VALUE not in {item.check for item in findings}


def test_scale_drift_order_of_magnitude_on_stable_weather() -> None:
    records = _series(40, boiler_recent=50.0, boiler_older=5.0)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF, primary_method="pbl")
    assert (
        HealthCheckName.SCALE_DRIFT.value,
        HealthSourceKind.GENERATOR.value,
        "boiler",
    ) in _names(findings)


def test_scale_drift_skips_seasonal_weather_change() -> None:
    """Heat drop with a matching degree-day drop is not a sensor unit change."""
    records: list[DailyRecord] = []
    start = AS_OF - timedelta(days=39)
    for offset in range(40):
        day = start + timedelta(days=offset)
        from_end = (AS_OF - day).days
        if from_end < 15:
            records.append(_record(day, boiler=2.0, hp=2.0, dd=1.0))
        else:
            records.append(_record(day, boiler=20.0, hp=20.0, dd=12.0))
    findings = run_health_checks(records, site=_site(), as_of=AS_OF, primary_method="pbl")
    assert HealthCheckName.SCALE_DRIFT not in {item.check for item in findings}


def test_scale_drift_room_demand() -> None:
    records = _series(40)
    rooms = _room_days("living", 40, 1.0, recent=20.0, older=2.0)
    findings = run_health_checks(
        records, site=_site(), room_records=rooms, as_of=AS_OF, primary_method="pbl"
    )
    assert (
        HealthCheckName.SCALE_DRIFT.value,
        HealthSourceKind.ROOM.value,
        "living",
    ) in _names(findings)


def test_weather_stalled_knmi_beyond_two_days() -> None:
    records = _series(20, provisional_days=3)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert (
        HealthCheckName.WEATHER_STALLED.value,
        HealthSourceKind.WEATHER.value,
        "knmi_380",
    ) in _names(findings)
    hit = next(item for item in findings if item.check is HealthCheckName.WEATHER_STALLED)
    assert hit.value == 3.0
    assert hit.typical == 2.0


def test_weather_stalled_not_routine_knmi_lag() -> None:
    records = _series(20, provisional_days=2)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    assert HealthCheckName.WEATHER_STALLED not in {item.check for item in findings}


def test_weather_stalled_open_meteo_uses_archive_delay() -> None:
    site = _site()
    site = Site(
        id=site.id,
        name=site.name,
        weather=WeatherSourceConfig(provider=Provider.OPEN_METEO),
        generators=site.generators,
        rooms=site.rooms,
    )
    eight = run_health_checks(_series(20, provisional_days=8), site=site, as_of=AS_OF)
    nine = run_health_checks(_series(20, provisional_days=9), site=site, as_of=AS_OF)
    assert HealthCheckName.WEATHER_STALLED not in {item.check for item in eight}
    assert (
        HealthCheckName.WEATHER_STALLED.value,
        HealthSourceKind.WEATHER.value,
        "open_meteo",
    ) in _names(nine)


def test_open_health_checks_attribute_payload() -> None:
    records = _series(20, stuck_boiler_days=3)
    findings = run_health_checks(records, site=_site(), as_of=AS_OF)
    rows = findings_as_attributes(findings)
    assert rows == [
        {
            "check": "stuck_value",
            "source_kind": "generator",
            "source_id": "boiler",
            "source_name": "CV",
            "hint": HINTS[HealthCheckName.STUCK_VALUE],
            "series": "carrier",
        }
    ]
    finding = findings[0]
    assert finding.issue_id("abc") == "health_abc_stuck_value_generator_boiler"


def test_stale_health_issue_ids_only_this_site() -> None:
    wanted = {"health_home_stuck_value_generator_boiler"}
    existing = [
        "health_home_stuck_value_generator_boiler",
        "health_home_weather_stalled_weather_knmi_380",
        "health_other_stuck_value_generator_boiler",
        "weather_check_home",
    ]
    assert stale_health_issue_ids(existing, wanted, "home") == {
        "health_home_weather_stalled_weather_knmi_380"
    }


def test_weather_source_ref_from_site() -> None:
    ref = WeatherSourceRef.from_site(_site())
    assert ref.provider == "knmi"
    assert ref.source_id == "knmi_380"
    assert "Maastricht" in ref.name


def test_custom_implausible_multiple() -> None:
    records = _series(40, last_boiler=20.0)
    default = run_health_checks(records, site=_site(), as_of=AS_OF)
    tight = run_health_checks(
        records,
        site=_site(),
        as_of=AS_OF,
        config=HealthCheckConfig(implausible_multiple=3.0),
    )
    assert HealthCheckName.IMPLAUSIBLE_VALUE not in {item.check for item in default}
    assert HealthCheckName.IMPLAUSIBLE_VALUE in {item.check for item in tight}
