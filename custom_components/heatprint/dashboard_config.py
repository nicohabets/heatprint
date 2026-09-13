"""Stock Heatprint Lovelace overview (no custom cards).

Entity ids follow ``has_entity_name`` with the English strings.json names, so
``Home`` + ``Space heating yesterday`` becomes ``sensor.home_space_heating_yesterday``.
Statistic ids stay on the metric keys (``heatprint:<site>_<metric>``).
ApexCharts is intentionally omitted so the dashboard loads on a stock frontend.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Metric keys match const.py / DATA_MODEL 2.2. This module stays HA-free for pytest.
_DOMAIN = "heatprint"
_METRIC_T_MEAN = "t_mean"
_METRIC_TAC_PBL = "tac_pbl"
_METRIC_TAC_HOUSE = "tac_house"
_METRIC_DD_CLASSIC = "dd_classic"
_METRIC_DD_KNMI14 = "dd_knmi14"
_METRIC_DD_PBL = "dd_pbl"
_METRIC_DD_HOUSE = "dd_house"
_METRIC_HEAT_SPACE = "heat_space"
_METRIC_HEAT_DHW = "heat_dhw"
_METRIC_ELECTRIC_HP = "electric_hp"
_METRIC_GAS = "gas"


def _statistic_id(site_id: str, metric: str) -> str:
    return f"{_DOMAIN}:{site_id}_{metric}"


def _generator_metric(generator_id: str) -> str:
    return f"heat_{generator_id}"


DASHBOARD_ICON = "mdi:home-thermometer-outline"
DASHBOARD_VIEW_PATH = "overview"

# slugify of the English entity names in strings.json (has_entity_name).
_SENSOR_OBJECT_IDS: dict[str, str] = {
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
}


def dashboard_url_path(site_id: str) -> str:
    """Return a Lovelace url_path that contains a hyphen (HA storage rule)."""
    slug = (site_id or "home").strip() or "home"
    return f"heatprint-{slug}"


def dashboard_title(site_name: str) -> str:
    """Return the sidebar title for a site."""
    name = (site_name or "").strip()
    return f"Heatprint ({name})" if name else "Heatprint"


def site_sensor_id(site_id: str, key: str) -> str:
    """Return ``sensor.<site>_<english_object_id>`` for a site sensor key."""
    return f"sensor.{site_id}_{_SENSOR_OBJECT_IDS[key]}"


def site_binary_sensor_id(site_id: str, key: str) -> str:
    """Return ``binary_sensor.<site>_<english_object_id>``."""
    return f"binary_sensor.{site_id}_{key}"


def build_overview_config(
    site_id: str,
    *,
    site_name: str = "Home",
    generators: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a Lovelace storage config for the stock Heatprint overview."""
    generators = list(generators or [])
    return {
        "views": [
            {
                "title": "Heatprint",
                "path": DASHBOARD_VIEW_PATH,
                "icon": DASHBOARD_ICON,
                "cards": _overview_cards(site_id, site_name, generators),
            }
        ]
    }


def _overview_cards(
    site_id: str, site_name: str, generators: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Return the masonry cards of the overview view."""
    generator_stats: list[dict[str, str]] = []
    for generator in generators:
        generator_id = str(generator.get("generator_id") or generator.get("id") or "")
        if not generator_id:
            continue
        name = str(generator.get("name") or generator_id)
        generator_stats.append(
            {
                "entity": _statistic_id(site_id, _generator_metric(generator_id)),
                "name": name,
            }
        )
    generator_stats.extend(
        [
            {
                "entity": _statistic_id(site_id, _METRIC_ELECTRIC_HP),
                "name": "Heat pump electricity",
            },
            {"entity": _statistic_id(site_id, _METRIC_GAS), "name": "Gas (m³)"},
        ]
    )
    return [
        {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "markdown",
                    "content": (
                        f"**Heat demand, weather-corrected — {site_name}.** "
                        "Space heating is one line, whatever the heat source. "
                        "Degree days are shown for the primary method; the other "
                        "methods are attributes of the same sensors."
                    ),
                },
                {
                    "type": "entities",
                    "title": "Today",
                    "entities": [
                        site_sensor_id(site_id, "effective_temperature"),
                        site_sensor_id(site_id, "degree_days_yesterday"),
                        site_sensor_id(site_id, "heat_space_yesterday"),
                        site_sensor_id(site_id, "cop_yesterday"),
                        site_sensor_id(site_id, "data_quality"),
                        site_binary_sensor_id(site_id, "data_gap"),
                        site_sensor_id(site_id, "last_weather_update"),
                    ],
                },
                {
                    "type": "entities",
                    "title": "Season to date",
                    "entities": [
                        site_sensor_id(site_id, "degree_days_season"),
                        site_sensor_id(site_id, "heat_space_season"),
                        site_sensor_id(site_id, "heat_dhw_season"),
                        site_sensor_id(site_id, "heat_per_degree_day"),
                        site_sensor_id(site_id, "gas_per_degree_day"),
                        site_sensor_id(site_id, "heat_pump_share_season"),
                        site_sensor_id(site_id, "dhw_baseline"),
                    ],
                },
                {
                    "type": "entities",
                    "title": "Energy signature and forecast",
                    "entities": [
                        site_sensor_id(site_id, "heat_loss_coefficient"),
                        site_sensor_id(site_id, "balance_temperature"),
                        site_sensor_id(site_id, "fit_quality"),
                        site_sensor_id(site_id, "forecast_heat_season"),
                        site_sensor_id(site_id, "forecast_gas_season"),
                        site_sensor_id(site_id, "forecast_electric_season"),
                    ],
                },
            ],
        },
        {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "statistics-graph",
                    "title": "Space heating and hot water per day (kWh)",
                    "chart_type": "bar",
                    "period": "day",
                    "days_to_show": 60,
                    "stat_types": ["change"],
                    "entities": [
                        {
                            "entity": _statistic_id(site_id, _METRIC_HEAT_SPACE),
                            "name": "Space heating",
                        },
                        {
                            "entity": _statistic_id(site_id, _METRIC_HEAT_DHW),
                            "name": "Hot water and cooking",
                        },
                    ],
                },
                {
                    "type": "statistics-graph",
                    "title": "Degree days per day, four methods (K)",
                    "chart_type": "line",
                    "period": "day",
                    "days_to_show": 60,
                    "stat_types": ["change"],
                    "entities": [
                        {
                            "entity": _statistic_id(site_id, _METRIC_DD_CLASSIC),
                            "name": "Classic (mindergas)",
                        },
                        {
                            "entity": _statistic_id(site_id, _METRIC_DD_KNMI14),
                            "name": "KNMI 14 °C",
                        },
                        {
                            "entity": _statistic_id(site_id, _METRIC_DD_PBL),
                            "name": "PBL 2022",
                        },
                        {
                            "entity": _statistic_id(site_id, _METRIC_DD_HOUSE),
                            "name": "House fit",
                        },
                    ],
                },
                {
                    "type": "statistics-graph",
                    "title": "Outdoor and effective temperature (°C)",
                    "chart_type": "line",
                    "period": "day",
                    "days_to_show": 60,
                    "stat_types": ["mean"],
                    "entities": [
                        {
                            "entity": _statistic_id(site_id, _METRIC_T_MEAN),
                            "name": "Mean temperature",
                        },
                        {
                            "entity": _statistic_id(site_id, _METRIC_TAC_PBL),
                            "name": "Effective (PBL)",
                        },
                        {
                            "entity": _statistic_id(site_id, _METRIC_TAC_HOUSE),
                            "name": "Effective (house)",
                        },
                    ],
                },
                {
                    "type": "statistics-graph",
                    "title": "Heat per generator per month (kWh)",
                    "chart_type": "bar",
                    "period": "month",
                    "days_to_show": 730,
                    "stat_types": ["change"],
                    "entities": generator_stats,
                },
            ],
        },
    ]
