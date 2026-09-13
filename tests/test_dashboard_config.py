"""Stock Heatprint Lovelace overview builder (no Home Assistant import)."""

from __future__ import annotations

import json

from dashboard_config import (
    build_overview_config,
    dashboard_title,
    dashboard_url_path,
    site_sensor_id,
)


def test_url_path_contains_hyphen() -> None:
    assert dashboard_url_path("home") == "heatprint-home"
    assert dashboard_url_path("my_house") == "heatprint-my_house"
    assert "-" in dashboard_url_path("")


def test_title_includes_site_name() -> None:
    assert dashboard_title("Heerlen") == "Heatprint (Heerlen)"
    assert dashboard_title("") == "Heatprint"


def test_english_entity_ids_match_has_entity_name() -> None:
    assert site_sensor_id("home", "heat_space_yesterday") == "sensor.home_space_heating_yesterday"
    assert (
        site_sensor_id("home", "forecast_electric_season")
        == "sensor.home_forecast_electricity_season"
    )
    assert site_sensor_id("my_house", "dhw_baseline") == "sensor.my_house_hot_water_baseline"


def test_overview_substitutes_site_and_omits_custom_cards() -> None:
    config = build_overview_config(
        "heerlen",
        site_name="Heerlen",
        generators=[{"generator_id": "boiler", "name": "Gas boiler"}],
    )
    dumped = json.dumps(config)
    assert "custom:apexcharts-card" not in dumped
    assert "sensor.heerlen_space_heating_yesterday" in dumped
    assert "heatprint:heerlen_heat_space" in dumped
    assert "heatprint:heerlen_heat_boiler" in dumped
    assert "heatprint:heerlen_dd_pbl" in dumped
    assert config["views"][0]["path"] == "overview"
    assert config["views"][0]["title"] == "Heatprint"
    cards = config["views"][0]["cards"]
    assert all(card["type"] in {"vertical-stack", "entities", "markdown"} or True for card in cards)
    types = {card["type"] for card in cards}
    assert types == {"vertical-stack"}
