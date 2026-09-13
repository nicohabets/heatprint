"""Stock Heatprint Lovelace overview builder (no Home Assistant import)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from dashboard_config import (
    MISSING_ENTITIES_NOTE,
    OVERVIEW_ENTITY_SPECS,
    build_overview_config,
    dashboard_title,
    dashboard_url_path,
    resolve_overview_entity_ids,
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


def test_title_includes_site_name() -> None:
    assert dashboard_title("Heerlen") == "Heatprint (Heerlen)"
    assert dashboard_title("") == "Heatprint"


def test_unique_id_matches_sensor_and_binary_sensor() -> None:
    assert site_entity_unique_id("abc123", "heat_space_yesterday") == "abc123_heat_space_yesterday"
    assert site_entity_unique_id("abc123", "data_gap") == "abc123_data_gap"

    sensor_src = (INTEGRATION / "sensor.py").read_text(encoding="utf-8")
    binary_src = (INTEGRATION / "binary_sensor.py").read_text(encoding="utf-8")
    assert 'f"{coordinator.entry.entry_id}_{description.key}"' in sensor_src
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
