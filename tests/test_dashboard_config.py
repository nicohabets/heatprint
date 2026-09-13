"""Stock Heatprint Lovelace overview builder (no Home Assistant import)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from dashboard_config import (
    MISSING_ENTITIES_NOTE,
    MISSING_ROOMS_NOTE,
    OVERVIEW_ENTITY_SPECS,
    ROOM_ENTITY_KEYS,
    ROOMS_DASHBOARD_VIEW_PATH,
    build_overview_config,
    build_rooms_config,
    dashboard_title,
    dashboard_url_path,
    resolve_overview_entity_ids,
    resolve_rooms_entity_ids,
    room_entity_unique_id,
    rooms_dashboard_title,
    rooms_dashboard_url_path,
    site_entity_unique_id,
)

REPO = Path(__file__).resolve().parents[1]
INTEGRATION = REPO / "custom_components" / "heatprint"

# English has_entity_name slugs (strings.json). Used only as mocked resolved ids.
_ENGLISH_OBJECT_IDS: dict[str, str] = {
    "effective_temperature": "effective_temperature",
    "degree_days_yesterday": "degree_days_yesterday",
    "degree_days_season": "degree_days_season",
    "heat_space_yesterday": "space_heating_yesterday",
    "heat_space_season": "space_heating_season",
    "heat_dhw_season": "hot_water_season",
    "heat_per_degree_day": "heat_per_degree_day",
    "gas_per_degree_day": "gas_per_degree_day",
    "heat_pump_share_season": "heat_pump_share_season",
    "cop_yesterday": "cop_yesterday",
    "heat_loss_coefficient": "heat_loss_coefficient",
    "balance_temperature": "balance_temperature",
    "fit_quality": "fit_quality",
    "forecast_heat_season": "forecast_heat_season",
    "forecast_gas_season": "forecast_gas_season",
    "forecast_electric_season": "forecast_electricity_season",
    "dhw_baseline": "hot_water_baseline",
    "data_quality": "data_quality",
    "last_weather_update": "last_weather_update",
    "data_gap": "data_gap",
    "heat_unallocated_season": "unallocated_heat_season",
    "most_expensive_room": "most_expensive_room",
}

# Dutch has_entity_name slugs (translations/nl.json) for site "Thuis".
_DUTCH_OBJECT_IDS: dict[str, str] = {
    "effective_temperature": "effectieve_temperatuur",
    "degree_days_yesterday": "graaddagen_gisteren",
    "degree_days_season": "graaddagen_seizoen",
    "heat_space_yesterday": "ruimteverwarming_gisteren",
    "heat_space_season": "ruimteverwarming_seizoen",
    "heat_dhw_season": "tapwater_seizoen",
    "heat_per_degree_day": "warmte_per_graaddag",
    "gas_per_degree_day": "gas_per_graaddag",
    "heat_pump_share_season": "aandeel_warmtepomp_seizoen",
    "cop_yesterday": "cop_gisteren",
    "heat_loss_coefficient": "warmteverliescoefficient",
    "balance_temperature": "balanstemperatuur",
    "fit_quality": "fitkwaliteit",
    "forecast_heat_season": "prognose_warmte_seizoen",
    "forecast_gas_season": "prognose_gas_seizoen",
    "forecast_electric_season": "prognose_stroom_seizoen",
    "dhw_baseline": "basislijn_tapwater",
    "data_quality": "datakwaliteit",
    "last_weather_update": "laatste_weerupdate",
    "data_gap": "datagat",
    "heat_unallocated_season": "niet_toegewezen_warmte_seizoen",
    "most_expensive_room": "duurste_kamer",
}

# Room sensor slugs (has_entity_name on the room device).
_ENGLISH_ROOM_OBJECT_IDS: dict[str, str] = {
    "room_heat_yesterday": "heat_yesterday",
    "room_heat_season": "heat_season",
    "room_share_season": "share_season",
    "room_heat_loss_coefficient": "heat_loss_coefficient",
    "room_specific_heat_loss": "specific_heat_loss",
    "room_balance_temperature": "balance_temperature",
    "room_fit_quality": "fit_quality",
    "room_heat_per_m2_season": "heat_per_m2_season",
    "room_data_quality": "data_quality",
}

_DUTCH_ROOM_OBJECT_IDS: dict[str, str] = {
    "room_heat_yesterday": "warmte_gisteren",
    "room_heat_season": "warmte_seizoen",
    "room_share_season": "aandeel_seizoen",
    "room_heat_loss_coefficient": "warmteverliescoefficient",
    "room_specific_heat_loss": "specifiek_warmteverlies",
    "room_balance_temperature": "balanstemperatuur",
    "room_fit_quality": "fitkwaliteit",
    "room_heat_per_m2_season": "warmte_per_m2_seizoen",
    "room_data_quality": "datakwaliteit",
}


class FakeEntityRegistry:
    """Minimal stand-in for ``entity_registry.EntityRegistry.async_get_entity_id``."""

    def __init__(self, entries: dict[tuple[str, str, str], str]) -> None:
        self._entries = entries

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str) -> str | None:
        return self._entries.get((domain, platform, unique_id))


def _registry_for(entry_id: str, site_id: str, object_ids: dict[str, str]) -> FakeEntityRegistry:
    entries: dict[tuple[str, str, str], str] = {}
    for domain, key in OVERVIEW_ENTITY_SPECS:
        slug = object_ids[key]
        entity_id = f"{domain}.{site_id}_{slug}"
        entries[(domain, "heatprint", site_entity_unique_id(entry_id, key))] = entity_id
    return FakeEntityRegistry(entries)


def _english_entity_ids(site_id: str) -> dict[str, str]:
    return {
        key: f"{domain}.{site_id}_{_ENGLISH_OBJECT_IDS[key]}"
        for domain, key in OVERVIEW_ENTITY_SPECS
    }


def _dutch_entity_ids(site_id: str) -> dict[str, str]:
    return {
        key: f"{domain}.{site_id}_{_DUTCH_OBJECT_IDS[key]}" for domain, key in OVERVIEW_ENTITY_SPECS
    }


def test_url_path_contains_hyphen() -> None:
    assert dashboard_url_path("home") == "heatprint-home"
    assert dashboard_url_path("my_house") == "heatprint-my_house"
    assert "-" in dashboard_url_path("")
    assert rooms_dashboard_url_path("home") == "heatprint-home-rooms"
    assert "-" in rooms_dashboard_url_path("thuis")


def test_title_includes_site_name() -> None:
    assert dashboard_title("Heerlen") == "Heatprint (Heerlen)"
    assert dashboard_title("") == "Heatprint"
    assert rooms_dashboard_title("Heerlen") == "Heatprint Rooms (Heerlen)"
    assert rooms_dashboard_title("") == "Heatprint Rooms"


def test_unique_id_matches_sensor_and_binary_sensor() -> None:
    assert site_entity_unique_id("abc123", "heat_space_yesterday") == "abc123_heat_space_yesterday"
    assert site_entity_unique_id("abc123", "data_gap") == "abc123_data_gap"
    assert (
        room_entity_unique_id("abc123", "living", "room_heat_yesterday")
        == "abc123_living_room_heat_yesterday"
    )

    sensor_src = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    binary_src = (INTEGRATION / "binary_sensor.py").read_text(encoding="utf-8")
    assert 'f"{coordinator.entry.entry_id}_{description.key}"' in sensor_src
    assert 'f"{coordinator.entry.entry_id}_{room.room_id}_{description.key}"' in sensor_src
    assert 'f"{coordinator.entry.entry_id}_{BINARY_SENSOR_DATA_GAP}"' in binary_src


def test_dashboard_config_has_no_homeassistant_imports() -> None:
    tree = ast.parse((INTEGRATION / "dashboard_config.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("homeassistant")
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("homeassistant")


def test_resolve_english_object_ids_from_mock_registry() -> None:
    entry_id = "entry-home"
    registry = _registry_for(entry_id, "home", _ENGLISH_OBJECT_IDS)
    resolved = resolve_overview_entity_ids(registry.async_get_entity_id, entry_id)
    assert resolved["heat_space_yesterday"] == "sensor.home_space_heating_yesterday"
    assert resolved["forecast_electric_season"] == "sensor.home_forecast_electricity_season"
    assert resolved["dhw_baseline"] == "sensor.home_hot_water_baseline"
    assert resolved["data_gap"] == "binary_sensor.home_data_gap"
    assert set(resolved) == {key for _domain, key in OVERVIEW_ENTITY_SPECS}


def test_resolve_dutch_object_ids_from_mock_registry() -> None:
    entry_id = "entry-thuis"
    registry = _registry_for(entry_id, "thuis", _DUTCH_OBJECT_IDS)
    resolved = resolve_overview_entity_ids(registry.async_get_entity_id, entry_id)
    assert resolved["heat_space_yesterday"] == "sensor.thuis_ruimteverwarming_gisteren"
    assert resolved["heat_space_season"] == "sensor.thuis_ruimteverwarming_seizoen"
    assert resolved["dhw_baseline"] == "sensor.thuis_basislijn_tapwater"
    assert resolved["data_gap"] == "binary_sensor.thuis_datagat"
    assert resolved["data_quality"] == "sensor.thuis_datakwaliteit"
    assert "space_heating_yesterday" not in resolved["heat_space_yesterday"]
    assert set(resolved) == {key for _domain, key in OVERVIEW_ENTITY_SPECS}


def test_overview_uses_english_resolved_ids_and_keeps_statistics() -> None:
    config = build_overview_config(
        "heerlen",
        site_name="Heerlen",
        generators=[{"generator_id": "boiler", "name": "Gas boiler"}],
        entity_ids=_english_entity_ids("heerlen"),
    )
    dumped = json.dumps(config)
    assert "custom:apexcharts-card" not in dumped
    assert "sensor.heerlen_space_heating_yesterday" in dumped
    assert "sensor.heerlen_hot_water_baseline" in dumped
    assert "binary_sensor.heerlen_data_gap" in dumped
    assert "heatprint:heerlen_heat_space" in dumped
    assert "heatprint:heerlen_heat_boiler" in dumped
    assert "heatprint:heerlen_dd_pbl" in dumped
    assert config["views"][0]["path"] == "overview"
    assert config["views"][0]["title"] == "Heatprint"
    types = {card["type"] for card in config["views"][0]["cards"]}
    assert types == {"vertical-stack"}
    entity_cards = [
        nested
        for card in config["views"][0]["cards"]
        for nested in card["cards"]
        if nested["type"] == "entities"
    ]
    assert {card["title"] for card in entity_cards} == {
        "Today",
        "Season to date",
        "Energy signature and forecast",
    }


def test_overview_uses_dutch_resolved_ids_not_english_guesses() -> None:
    config = build_overview_config(
        "thuis",
        site_name="Thuis",
        generators=[{"generator_id": "cv_ketel", "name": "CV-ketel"}],
        entity_ids=_dutch_entity_ids("thuis"),
    )
    dumped = json.dumps(config)
    assert "sensor.thuis_ruimteverwarming_gisteren" in dumped
    assert "sensor.thuis_ruimteverwarming_seizoen" in dumped
    assert "sensor.thuis_tapwater_seizoen" in dumped
    assert "sensor.thuis_basislijn_tapwater" in dumped
    assert "binary_sensor.thuis_datagat" in dumped
    assert "sensor.thuis_space_heating_yesterday" not in dumped
    assert "sensor.thuis_hot_water_season" not in dumped
    assert "binary_sensor.thuis_data_gap" not in dumped
    # Statistic ids stay on metric keys (language-independent).
    assert "heatprint:thuis_heat_space" in dumped
    assert "heatprint:thuis_heat_dhw" in dumped
    assert "heatprint:thuis_heat_cv_ketel" in dumped
    assert "heatprint:thuis_dd_pbl" in dumped
    assert "heatprint:thuis_t_mean" in dumped


def test_resolve_then_build_matches_registry_language() -> None:
    """The create_dashboard path: registry lookup, then build, for NL and EN."""
    cases = (
        ("entry-en", "home", "Home", _ENGLISH_OBJECT_IDS, "sensor.home_space_heating_yesterday"),
        (
            "entry-nl",
            "thuis",
            "Thuis",
            _DUTCH_OBJECT_IDS,
            "sensor.thuis_ruimteverwarming_gisteren",
        ),
    )
    for entry_id, site_id, site_name, object_ids, expected in cases:
        registry = _registry_for(entry_id, site_id, object_ids)
        resolved = resolve_overview_entity_ids(registry.async_get_entity_id, entry_id)
        dumped = json.dumps(
            build_overview_config(site_id, site_name=site_name, entity_ids=resolved)
        )
        assert expected in dumped
        assert f"heatprint:{site_id}_heat_space" in dumped


def test_unregistered_entities_are_omitted_not_guessed() -> None:
    entity_ids = {
        "effective_temperature": "sensor.thuis_effectieve_temperatuur",
        "heat_space_yesterday": "sensor.thuis_ruimteverwarming_gisteren",
    }
    config = build_overview_config("thuis", site_name="Thuis", entity_ids=entity_ids)
    today = config["views"][0]["cards"][0]["cards"][1]
    assert today["type"] == "entities"
    assert today["entities"] == [
        "sensor.thuis_effectieve_temperatuur",
        "sensor.thuis_ruimteverwarming_gisteren",
    ]
    dumped = json.dumps(config)
    assert "sensor.thuis_space_heating_yesterday" not in dumped
    assert "sensor.thuis_degree_days_yesterday" not in dumped
    season = config["views"][0]["cards"][0]["cards"][2]
    assert season["type"] == "markdown"
    assert MISSING_ENTITIES_NOTE in season["content"]
    assert "heatprint:thuis_heat_space" in dumped


def test_empty_registry_uses_markdown_notes_not_dead_ids() -> None:
    registry = FakeEntityRegistry({})
    resolved = resolve_overview_entity_ids(registry.async_get_entity_id, "missing")
    assert resolved == {}
    config = build_overview_config("thuis", site_name="Thuis", entity_ids=resolved)
    dumped = json.dumps(config)
    assert "sensor.thuis_" not in dumped
    assert "binary_sensor.thuis_" not in dumped
    assert dumped.count(MISSING_ENTITIES_NOTE) == 3
    assert "heatprint:thuis_heat_space" in dumped
    notes = [
        nested
        for card in config["views"][0]["cards"]
        for nested in card["cards"]
        if nested["type"] == "markdown" and MISSING_ENTITIES_NOTE in nested.get("content", "")
    ]
    assert {note["content"].split(".**")[0] for note in notes} == {
        "**Today",
        "**Season to date",
        "**Energy signature and forecast",
    }


def _rooms_payload() -> list[dict[str, str]]:
    return [{"room_id": "living", "name": "Living"}, {"room_id": "bath", "name": "Bath"}]


def _rooms_registry(
    entry_id: str, site_id: str, room_object_ids: dict[str, str], site_object_ids: dict[str, str]
) -> FakeEntityRegistry:
    entries: dict[tuple[str, str, str], str] = {}
    for key in ("heat_unallocated_season", "most_expensive_room"):
        slug = site_object_ids[key]
        entries[("sensor", "heatprint", site_entity_unique_id(entry_id, key))] = (
            f"sensor.{site_id}_{slug}"
        )
    for room_id, device_slug in (("living", "living"), ("bath", "bath")):
        for key, slug in room_object_ids.items():
            unique = room_entity_unique_id(entry_id, room_id, key)
            entries[("sensor", "heatprint", unique)] = f"sensor.{site_id}_{device_slug}_{slug}"
    return FakeEntityRegistry(entries)


def test_resolve_dutch_room_object_ids_from_mock_registry() -> None:
    entry_id = "entry-thuis"
    registry = _rooms_registry(entry_id, "thuis", _DUTCH_ROOM_OBJECT_IDS, _DUTCH_OBJECT_IDS)
    resolved = resolve_rooms_entity_ids(
        registry.async_get_entity_id, entry_id, _rooms_payload()
    )
    assert resolved["heat_unallocated_season"] == "sensor.thuis_niet_toegewezen_warmte_seizoen"
    assert resolved["most_expensive_room"] == "sensor.thuis_duurste_kamer"
    assert resolved["rooms"]["living"]["room_heat_yesterday"] == (
        "sensor.thuis_living_warmte_gisteren"
    )
    assert resolved["rooms"]["living"]["room_heat_loss_coefficient"] == (
        "sensor.thuis_living_warmteverliescoefficient"
    )
    assert "heat_yesterday" not in resolved["rooms"]["living"]["room_heat_yesterday"]
    assert set(resolved["rooms"]["living"]) == set(ROOM_ENTITY_KEYS)


def test_rooms_dashboard_uses_dutch_resolved_ids_not_english_guesses() -> None:
    entry_id = "entry-thuis"
    registry = _rooms_registry(entry_id, "thuis", _DUTCH_ROOM_OBJECT_IDS, _DUTCH_OBJECT_IDS)
    resolved = resolve_rooms_entity_ids(
        registry.async_get_entity_id, entry_id, _rooms_payload()
    )
    config = build_rooms_config(
        "thuis",
        site_name="Thuis",
        rooms=[{"room_id": "living", "name": "Woonkamer"}, {"room_id": "bath", "name": "Badkamer"}],
        entity_ids=resolved,
    )
    dumped = json.dumps(config)
    assert config["views"][0]["path"] == ROOMS_DASHBOARD_VIEW_PATH
    assert config["views"][0]["title"] == "Rooms"
    assert "sensor.thuis_niet_toegewezen_warmte_seizoen" in dumped
    assert "sensor.thuis_duurste_kamer" in dumped
    assert "sensor.thuis_living_warmte_gisteren" in dumped
    assert "sensor.thuis_living_warmte_seizoen" in dumped
    assert "sensor.thuis_living_heat_yesterday" not in dumped
    assert "sensor.thuis_unallocated_heat_season" not in dumped
    assert "heatprint:thuis_heat_unallocated" in dumped
    assert "heatprint:thuis_room_living_heat" in dumped
    assert "heatprint:thuis_room_bath_heat" in dumped
    assert "heatprint:thuis_heat_space" in dumped
    assert "custom:apexcharts-card" not in dumped


def test_rooms_dashboard_uses_english_resolved_ids() -> None:
    entry_id = "entry-home"
    registry = _rooms_registry(entry_id, "home", _ENGLISH_ROOM_OBJECT_IDS, _ENGLISH_OBJECT_IDS)
    resolved = resolve_rooms_entity_ids(
        registry.async_get_entity_id, entry_id, _rooms_payload()
    )
    config = build_rooms_config(
        "home", site_name="Home", rooms=_rooms_payload(), entity_ids=resolved
    )
    dumped = json.dumps(config)
    assert "sensor.home_unallocated_heat_season" in dumped
    assert "sensor.home_most_expensive_room" in dumped
    assert "sensor.home_living_heat_yesterday" in dumped
    assert "heatprint:home_room_living_heat" in dumped


def test_rooms_dashboard_empty_rooms_has_note_not_dead_ids() -> None:
    config = build_rooms_config("thuis", site_name="Thuis", rooms=[], entity_ids={})
    dumped = json.dumps(config)
    assert MISSING_ROOMS_NOTE in dumped
    assert "sensor.thuis_" not in dumped
    assert "heatprint:thuis_heat_unallocated" in dumped
    assert "heatprint:thuis_heat_space" in dumped


def test_overview_includes_unallocated_when_registered() -> None:
    entity_ids = _dutch_entity_ids("thuis")
    config = build_overview_config("thuis", site_name="Thuis", entity_ids=entity_ids)
    dumped = json.dumps(config)
    assert "sensor.thuis_niet_toegewezen_warmte_seizoen" in dumped
    assert "sensor.thuis_duurste_kamer" in dumped


def test_room_sensor_keys_match_dashboard_and_translations() -> None:
    """Dashboard keys, sensor.py and NL/EN names stay aligned (Dutch UI slugs)."""
    sensor_src = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    for key in ROOM_ENTITY_KEYS:
        assert f'key={key}' in sensor_src or f'key=SENSOR_{key.upper()}' in sensor_src
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    nl = json.loads((INTEGRATION / "translations" / "nl.json").read_text(encoding="utf-8"))
    en = json.loads((INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8"))
    for key in (*ROOM_ENTITY_KEYS, "heat_unallocated_season", "most_expensive_room"):
        assert key in strings["entity"]["sensor"]
        assert key in nl["entity"]["sensor"]
        assert en["entity"]["sensor"][key] == strings["entity"]["sensor"][key]
    assert nl["entity"]["sensor"]["room_heat_yesterday"]["name"] == "Warmte gisteren"
    assert nl["entity"]["sensor"]["most_expensive_room"]["name"] == "Duurste kamer"
    assert "rooms" in strings["options"]["step"]["init"]["menu_options"]
    assert nl["options"]["step"]["init"]["menu_options"]["rooms"] == "Kamers"
