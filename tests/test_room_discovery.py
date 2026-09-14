"""HA-area room discovery and idempotent sync plan (METHODS §12.6)."""

from __future__ import annotations

from types import SimpleNamespace

from first_run import default_entry_options, default_weather_config
from history_values import (
    demand_requires_history,
    heating_from_sample,
    temperature_from_sample,
    value_from_sample,
)
from room_discovery import (
    SKIP_EXCLUDED,
    SKIP_NO_HEATING_CIRCUIT,
    SKIP_NO_SIGNAL,
    DiscoveryResult,
    RegistryArea,
    RegistryEntity,
    discover_rooms,
)
from room_sync import (
    ExistingRoom,
    area_unique_id,
    auto_sync_enabled,
    exclude_area_ids_from_options,
    existing_room_from_data,
    plan_room_sync,
)
from site_defaults import resolve_site_defaults, site_defaults_from_hass


def _entity(
    entity_id: str,
    area_id: str | None,
    *,
    name: str | None = None,
    unit: str | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    state: str | None = None,
    attributes: dict | None = None,
) -> RegistryEntity:
    return RegistryEntity(
        entity_id=entity_id,
        area_id=area_id,
        name=name or entity_id,
        unit=unit,
        device_class=device_class,
        state_class=state_class,
        state=state,
        attributes=attributes or {},
    )


def _nico_fixture() -> tuple[list[RegistryArea], list[RegistryEntity]]:
    """Areas and entities modelled on Nico's Tado/`tado_ce` house (METHODS §12.6)."""
    areas = [
        RegistryArea("woonkamer", "Woonkamer"),
        RegistryArea("serre", "Serre"),
        RegistryArea("slaapkamer", "Slaapkamer"),
        RegistryArea("keldertrap", "Keldertrap"),
        RegistryArea("overloop", "Overloop"),
        RegistryArea("sauna", "Sauna"),
        RegistryArea("toilet", "Toilet"),
        RegistryArea("hal", "Hal"),
        RegistryArea("garage", "Garage"),
    ]
    entities = [
        _entity("climate.woonkamer", "woonkamer", state="heat", attributes={"hvac_action": "idle"}),
        _entity(
            "sensor.woonkamer_woonkamer_verwarming",
            "woonkamer",
            unit="%",
            state_class="measurement",
        ),
        _entity("climate.serre", "serre"),
        _entity("sensor.serre_serre_verwarming", "serre", unit="%", state_class="measurement"),
        _entity(
            "climate.slaapkamer", "slaapkamer", state="heat", attributes={"hvac_action": "heating"}
        ),
        _entity("climate.keldertrap", "keldertrap"),
        _entity("select.keldertrap_heating_circuit", "keldertrap", state="no_heating_circuit"),
        _entity("climate.overloop", "overloop"),
        _entity("select.overloop_heating_circuit", "overloop", state="no_heating_circuit"),
        _entity("climate.sauna", "sauna"),
        _entity("select.sauna_heating_circuit", "sauna", state="no_heating_circuit"),
        _entity("climate.toilet", "toilet"),
        _entity("select.toilet_heating_circuit", "toilet", state="no_heating_circuit"),
        _entity("light.hal", "hal"),
        _entity("climate.garage", "garage"),
        _entity("sensor.garage_valve_position", "garage", unit="%"),
    ]
    return areas, entities


def test_confirm_counts_are_short_not_entity_dumps() -> None:
    result = discover_rooms(*_nico_fixture())
    counts = result.confirm_counts()
    assert counts == {"room_count": "4", "skipped_count": "5"}
    assert "sensor." not in counts["room_count"]
    summary = result.room_summary()
    assert "sensor.woonkamer_woonkamer_verwarming" in summary
    assert "Keldertrap" in result.skipped_summary()


def test_nico_areas_skip_no_heating_and_empty_hal() -> None:
    rooms, skipped = (
        discover_rooms(*_nico_fixture()).rooms,
        discover_rooms(*_nico_fixture()).skipped,
    )
    names = {room.name for room in rooms}
    assert names == {"Woonkamer", "Serre", "Slaapkamer", "Garage"}
    skipped_by_name = {item.name: item.reason for item in skipped}
    assert skipped_by_name["Keldertrap"] == SKIP_NO_HEATING_CIRCUIT
    assert skipped_by_name["Overloop"] == SKIP_NO_HEATING_CIRCUIT
    assert skipped_by_name["Sauna"] == SKIP_NO_HEATING_CIRCUIT
    assert skipped_by_name["Toilet"] == SKIP_NO_HEATING_CIRCUIT
    assert skipped_by_name["Hal"] == SKIP_NO_SIGNAL


def test_demand_preference_percentage_then_valve_then_climate() -> None:
    result = discover_rooms(*_nico_fixture())
    by_name = {room.name: room for room in result.rooms}
    assert by_name["Woonkamer"].demand_kind == "percentage"
    assert by_name["Woonkamer"].demand_entity == "sensor.woonkamer_woonkamer_verwarming"
    assert by_name["Woonkamer"].temperature_entity == "climate.woonkamer"
    assert by_name["Slaapkamer"].demand_kind == "binary"
    assert by_name["Slaapkamer"].demand_entity == "climate.slaapkamer"
    assert by_name["Garage"].demand_kind == "valve_position"
    assert by_name["Garage"].demand_entity == "sensor.garage_valve_position"


def test_exclude_area_list() -> None:
    areas, entities = _nico_fixture()
    result = discover_rooms(areas, entities, exclude_area_ids=["woonkamer", "serre"])
    names = {room.name for room in result.rooms}
    assert "Woonkamer" not in names
    assert "Serre" not in names
    reasons = {item.area_id: item.reason for item in result.skipped}
    assert reasons["woonkamer"] == SKIP_EXCLUDED
    assert reasons["serre"] == SKIP_EXCLUDED


def test_underfloor_name_heuristic() -> None:
    areas = [RegistryArea("woonkamer", "Woonkamer vloerverwarming")]
    entities = [_entity("climate.woonkamer", "woonkamer")]
    room = discover_rooms(areas, entities).rooms[0]
    assert room.emitter_kind == "underfloor"


def test_humidity_percentage_is_not_demand() -> None:
    areas = [RegistryArea("badkamer", "Badkamer")]
    entities = [
        _entity("climate.badkamer", "badkamer"),
        _entity("sensor.badkamer_humidity", "badkamer", unit="%", device_class="humidity"),
    ]
    room = discover_rooms(areas, entities).rooms[0]
    assert room.demand_kind == "binary"
    assert room.demand_entity == "climate.badkamer"


def test_sync_creates_then_is_idempotent() -> None:
    discovery = discover_rooms(*_nico_fixture())
    first = plan_room_sync([], discovery)
    assert first.changed
    assert {op.action for op in first.ops} == {"create"}
    assert {op.unique_id for op in first.ops} == {
        area_unique_id("woonkamer"),
        area_unique_id("serre"),
        area_unique_id("slaapkamer"),
        area_unique_id("garage"),
    }
    existing = [
        existing_room_from_data(op.room, unique_id=op.unique_id, title=op.title) for op in first.ops
    ]
    second = plan_room_sync(existing, discovery)
    assert second.ops == ()


def test_sync_updates_entity_links_and_keeps_overrides() -> None:
    discovery = discover_rooms(*_nico_fixture())
    woonkamer = next(room for room in discovery.rooms if room.area_id == "woonkamer")
    existing = [
        ExistingRoom(
            room_id="woonkamer",
            name="Living",
            area_id="woonkamer",
            demand_entity="climate.woonkamer",
            demand_kind="binary",
            temperature_entity=None,
            emitter_kind="underfloor",
            rated_output_w=1200.0,
            floor_area_m2=32.0,
            volume_m3=None,
            price_entity=None,
            unique_id=area_unique_id("woonkamer"),
            subentry_id="sub_1",
        )
    ]
    plan = plan_room_sync(existing, DiscoveryResult(rooms=(woonkamer,), skipped=()))
    assert len(plan.ops) == 1
    op = plan.ops[0]
    assert op.action == "update"
    assert op.room["demand_entity"] == "sensor.woonkamer_woonkamer_verwarming"
    assert op.room["demand_kind"] == "percentage"
    assert op.room["temperature_entity"] == "climate.woonkamer"
    assert op.room["emitter_kind"] == "underfloor"
    assert op.room["rated_output_w"] == 1200.0
    assert op.room["floor_area_m2"] == 32.0
    assert op.room["name"] == "Living"


def test_sync_does_not_delete_missing_areas() -> None:
    existing = [
        ExistingRoom(
            room_id="zolder",
            name="Zolder",
            area_id="zolder",
            demand_entity="climate.zolder",
            demand_kind="binary",
            temperature_entity="climate.zolder",
            emitter_kind="radiator",
            rated_output_w=None,
            floor_area_m2=None,
            volume_m3=None,
            price_entity=None,
            unique_id=area_unique_id("zolder"),
        )
    ]
    plan = plan_room_sync(existing, discover_rooms(*_nico_fixture()))
    assert all(op.action != "delete" for op in plan.ops)
    assert all(op.room.get("room_id") != "zolder" for op in plan.ops)


def test_auto_sync_defaults_on() -> None:
    assert auto_sync_enabled({}) is True
    assert auto_sync_enabled({"rooms": {"auto_sync": False}}) is False
    assert exclude_area_ids_from_options({"rooms": {"exclude_area_ids": ["hal"]}}) == ["hal"]


def test_first_run_weather_and_options() -> None:
    nl = default_weather_config("NL", nearest_station_id="380")
    assert nl["provider"] == "knmi"
    assert nl["station_id"] == "380"
    assert nl["fallback"] == "open_meteo"
    intl = default_weather_config("DE")
    assert intl["provider"] == "open_meteo"
    options = default_entry_options()
    assert options["rooms"]["auto_sync"] is True
    assert options["rooms"]["exclude_area_ids"] == []
    assert options["methods"]["primary"] == "house"


def test_zone_home_name_wins_over_location_name() -> None:
    defaults = resolve_site_defaults(
        location_name="Home Assistant",
        home_name="Thuis",
        latitude=50.888,
        longitude=5.979,
        time_zone="Europe/Amsterdam",
        country="NL",
    )
    assert defaults.name == "Thuis"


def test_site_defaults_from_hass_reads_zone_home_name() -> None:
    hass = SimpleNamespace(
        config=SimpleNamespace(
            location_name="Home Assistant",
            latitude=50.85,
            longitude=5.69,
            time_zone="Europe/Amsterdam",
            country=None,
        ),
        states=SimpleNamespace(
            get=lambda _entity_id: SimpleNamespace(
                name="Thuis",
                attributes={"latitude": 1.0, "longitude": 2.0, "friendly_name": "Thuis"},
            )
        ),
    )
    defaults = site_defaults_from_hass(hass)
    assert defaults.name == "Thuis"
    assert defaults.country == "NL"


def test_climate_binary_uses_hvac_action_not_temperature() -> None:
    assert demand_requires_history("climate.slaapkamer", "binary") is True
    assert demand_requires_history("sensor.woonkamer_verwarming", "percentage") is False
    assert heating_from_sample("heat", {"hvac_action": "idle"}) == 0.0
    assert heating_from_sample("heat", {"hvac_action": "heating"}) == 1.0
    assert temperature_from_sample("heat", {"current_temperature": 20.5}) == 20.5
    assert (
        value_from_sample(
            "heat", {"hvac_action": "idle", "current_temperature": 20.5}, mode="heating"
        )
        == 0.0
    )
    assert (
        value_from_sample(
            "heat", {"hvac_action": "idle", "current_temperature": 20.5}, mode="temperature"
        )
        == 20.5
    )
