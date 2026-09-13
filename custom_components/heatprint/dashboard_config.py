"""Stock Heatprint Lovelace overview (no custom cards).

Entity cards are language-agnostic: they take already-resolved ``entity_id``s.
Home Assistant slugifies ``has_entity_name`` object ids from the UI language, so
English ``sensor.thuis_space_heating_yesterday`` is not the same as Dutch
``sensor.thuis_ruimteverwarming_gisteren``. The stable key is
``unique_id = {config_entry.entry_id}_{description.key}`` (see sensor.py /
binary_sensor.py). ``dashboard.py`` looks those up in the entity registry
before save.

Statistic ids stay on the metric keys (``heatprint:<site>_<metric>``).
ApexCharts is intentionally omitted so the dashboard loads on a stock frontend.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
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

# (entity domain, description.key) for every row on the overview entity cards.
# unique_id is always ``{config_entry.entry_id}_{key}``.
OVERVIEW_ENTITY_SPECS: tuple[tuple[str, str], ...] = (
    ("sensor", "effective_temperature"),
    ("sensor", "degree_days_yesterday"),
    ("sensor", "heat_space_yesterday"),
    ("sensor", "cop_yesterday"),
    ("sensor", "data_quality"),
    ("binary_sensor", "data_gap"),
    ("sensor", "last_weather_update"),
    ("sensor", "degree_days_season"),
    ("sensor", "heat_space_season"),
    ("sensor", "heat_dhw_season"),
    ("sensor", "heat_per_degree_day"),
    ("sensor", "gas_per_degree_day"),
    ("sensor", "heat_pump_share_season"),
    ("sensor", "dhw_baseline"),
    ("sensor", "heat_loss_coefficient"),
    ("sensor", "balance_temperature"),
    ("sensor", "fit_quality"),
    ("sensor", "forecast_heat_season"),
    ("sensor", "forecast_gas_season"),
    ("sensor", "forecast_electric_season"),
    ("sensor", "heat_unallocated_season"),
    ("sensor", "most_expensive_room"),
)

_TODAY_KEYS: tuple[str, ...] = (
    "effective_temperature",
    "degree_days_yesterday",
    "heat_space_yesterday",
    "cop_yesterday",
    "data_quality",
    "data_gap",
    "last_weather_update",
)
_SEASON_KEYS: tuple[str, ...] = (
    "degree_days_season",
    "heat_space_season",
    "heat_dhw_season",
    "heat_per_degree_day",
    "gas_per_degree_day",
    "heat_pump_share_season",
    "dhw_baseline",
    "heat_unallocated_season",
    "most_expensive_room",
)
_FIT_KEYS: tuple[str, ...] = (
    "heat_loss_coefficient",
    "balance_temperature",
    "fit_quality",
    "forecast_heat_season",
    "forecast_gas_season",
    "forecast_electric_season",
)

MISSING_ENTITIES_NOTE = (
    "Heatprint sensors are not registered yet. Reload the integration, then "
    "recreate the dashboard with `heatprint.create_dashboard`."
)

EntityIdLookup = Callable[[str, str, str], str | None]


def _statistic_id(site_id: str, metric: str) -> str:
    return f"{_DOMAIN}:{site_id}_{metric}"


def _generator_metric(generator_id: str) -> str:
    return f"heat_{generator_id}"


DASHBOARD_ICON = "mdi:home-thermometer-outline"
DASHBOARD_VIEW_PATH = "overview"


def dashboard_url_path(site_id: str) -> str:
    """Return a Lovelace url_path that contains a hyphen (HA storage rule)."""
    slug = (site_id or "home").strip() or "home"
    return f"heatprint-{slug}"


def dashboard_title(site_name: str) -> str:
    """Return the sidebar title for a site."""
    name = (site_name or "").strip()
    return f"Heatprint ({name})" if name else "Heatprint"


def site_entity_unique_id(entry_id: str, key: str) -> str:
    """Return ``{entry_id}_{description.key}`` used by site sensors and binary sensors."""
    return f"{entry_id}_{key}"


def resolve_overview_entity_ids(lookup: EntityIdLookup, entry_id: str) -> dict[str, str]:
    """Map description keys to current ``entity_id``s via the entity registry.

    ``lookup(domain, platform, unique_id)`` matches
    ``entity_registry.async_get_entity_id``. Keys that are not registered yet
    are omitted (the card builder skips those rows).
    """
    resolved: dict[str, str] = {}
    for domain, key in OVERVIEW_ENTITY_SPECS:
        entity_id = lookup(domain, _DOMAIN, site_entity_unique_id(entry_id, key))
        if entity_id:
            resolved[key] = entity_id
    return resolved


def build_overview_config(
    site_id: str,
    *,
    site_name: str = "Home",
    generators: Iterable[Mapping[str, Any]] | None = None,
    entity_ids: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a Lovelace storage config for the stock Heatprint overview.

    ``entity_ids`` maps description keys (``heat_space_yesterday``, ``data_gap``,
    …) to the current registry ``entity_id``. Statistic-graph cards do not use
    this map. Missing keys are omitted rather than written as guessed object ids.
    """
    generators = list(generators or [])
    return {
        "views": [
            {
                "title": "Heatprint",
                "path": DASHBOARD_VIEW_PATH,
                "icon": DASHBOARD_ICON,
                "cards": _overview_cards(site_id, site_name, generators, entity_ids or {}),
            }
        ]
    }


def _entity_rows(keys: tuple[str, ...], entity_ids: Mapping[str, str]) -> list[str]:
    """Return resolved entity_ids for keys that are present in the map."""
    return [entity_ids[key] for key in keys if key in entity_ids]


def _entities_or_note(
    title: str, keys: tuple[str, ...], entity_ids: Mapping[str, str]
) -> dict[str, Any]:
    """Build an entities card, or a markdown note when nothing is registered."""
    rows = _entity_rows(keys, entity_ids)
    if not rows:
        return {"type": "markdown", "content": f"**{title}.** {MISSING_ENTITIES_NOTE}"}
    return {"type": "entities", "title": title, "entities": rows}


def _overview_cards(
    site_id: str,
    site_name: str,
    generators: list[Mapping[str, Any]],
    entity_ids: Mapping[str, str],
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
                _entities_or_note("Today", _TODAY_KEYS, entity_ids),
                _entities_or_note("Season to date", _SEASON_KEYS, entity_ids),
                _entities_or_note("Energy signature and forecast", _FIT_KEYS, entity_ids),
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


# --- Rooms dashboard (sidebar path /heatprint-<site>-rooms) -------------------------------------

_METRIC_HEAT_UNALLOCATED = "heat_unallocated"

ROOMS_DASHBOARD_ICON = "mdi:floor-plan"
ROOMS_DASHBOARD_VIEW_PATH = "rooms"

# Site-level sensors that appear on the rooms dashboard.
ROOMS_SITE_ENTITY_SPECS: tuple[tuple[str, str], ...] = (
    ("sensor", "heat_unallocated_season"),
    ("sensor", "most_expensive_room"),
)

# Per-room description.keys. unique_id is ``{entry_id}_{room_id}_{key}``.
ROOM_ENTITY_KEYS: tuple[str, ...] = (
    "room_heat_yesterday",
    "room_heat_season",
    "room_share_season",
    "room_heat_loss_coefficient",
    "room_specific_heat_loss",
    "room_balance_temperature",
    "room_fit_quality",
    "room_heat_per_m2_season",
    "room_data_quality",
)

_ROOM_SUMMARY_KEYS: tuple[str, ...] = (
    "room_heat_yesterday",
    "room_heat_season",
    "room_share_season",
    "room_heat_loss_coefficient",
    "room_specific_heat_loss",
    "room_balance_temperature",
    "room_data_quality",
)

MISSING_ROOMS_NOTE = (
    "No rooms are configured yet. Add a Room subentry on the Heatprint site, "
    "reload, then recreate the dashboard with `heatprint.create_dashboard`."
)


def rooms_dashboard_url_path(site_id: str) -> str:
    """Return the Lovelace url_path of the rooms dashboard (contains a hyphen)."""
    return f"{dashboard_url_path(site_id)}-rooms"


def rooms_dashboard_title(site_name: str) -> str:
    """Return the sidebar title of the rooms dashboard."""
    name = (site_name or "").strip()
    return f"Heatprint Rooms ({name})" if name else "Heatprint Rooms"


def room_entity_unique_id(entry_id: str, room_id: str, key: str) -> str:
    """Return ``{entry_id}_{room_id}_{description.key}`` used by room sensors."""
    return f"{entry_id}_{room_id}_{key}"


def _room_heat_metric(room_id: str) -> str:
    return f"room_{room_id}_heat"


def _room_t_mean_metric(room_id: str) -> str:
    return f"room_{room_id}_t_mean"


def resolve_rooms_entity_ids(
    lookup: EntityIdLookup,
    entry_id: str,
    rooms: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Map site and per-room description keys to current ``entity_id``s.

    Site keys live at the top level. Per-room keys live under
    ``rooms[room_id][key]``. Missing registry rows are omitted.
    """
    resolved: dict[str, Any] = {"rooms": {}}
    for domain, key in ROOMS_SITE_ENTITY_SPECS:
        entity_id = lookup(domain, _DOMAIN, site_entity_unique_id(entry_id, key))
        if entity_id:
            resolved[key] = entity_id
    for room in rooms or []:
        room_id = str(room.get("room_id") or room.get("id") or "")
        if not room_id:
            continue
        per_room: dict[str, str] = {}
        for key in ROOM_ENTITY_KEYS:
            entity_id = lookup("sensor", _DOMAIN, room_entity_unique_id(entry_id, room_id, key))
            if entity_id:
                per_room[key] = entity_id
        if per_room:
            resolved["rooms"][room_id] = per_room
    return resolved


def build_rooms_config(
    site_id: str,
    *,
    site_name: str = "Home",
    rooms: Iterable[Mapping[str, Any]] | None = None,
    entity_ids: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a Lovelace storage config for the Rooms dashboard.

    ``entity_ids`` is the map from :func:`resolve_rooms_entity_ids`. Statistic
    graphs use language-independent ``heatprint:<site>_room_<id>_heat`` ids.
    """
    return {
        "views": [
            {
                "title": "Rooms",
                "path": ROOMS_DASHBOARD_VIEW_PATH,
                "icon": ROOMS_DASHBOARD_ICON,
                "cards": _rooms_cards(site_id, site_name, list(rooms or []), entity_ids or {}),
            }
        ]
    }


def _rooms_cards(
    site_id: str,
    site_name: str,
    rooms: list[Mapping[str, Any]],
    entity_ids: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return the masonry cards of the rooms view."""
    per_room_ids = entity_ids.get("rooms") if isinstance(entity_ids.get("rooms"), Mapping) else {}
    site_keys = ("heat_unallocated_season", "most_expensive_room")
    left: list[dict[str, Any]] = [
        {
            "type": "markdown",
            "content": (
                f"**Per-room space heating — {site_name}.** "
                "Heat is allocated from the site total using each room's demand "
                "signal (METHODS §12). Apparent UA includes interzonal exchange "
                "and is not an EN 12831 design figure. "
                "`most_expensive_room` is ranked by allocated heat until site "
                "cost statistics land (METHODS §13). After adding rooms, run "
                "`heatprint.create_dashboard` so this view picks up new sensors."
            ),
        },
        _entities_or_note("Site rooms summary", site_keys, entity_ids),
    ]
    if not rooms:
        left.append({"type": "markdown", "content": MISSING_ROOMS_NOTE})
    else:
        for room in rooms:
            room_id = str(room.get("room_id") or room.get("id") or "")
            if not room_id:
                continue
            name = str(room.get("name") or room_id)
            room_map = per_room_ids.get(room_id) if isinstance(per_room_ids, Mapping) else {}
            left.append(
                _entities_or_note(name, _ROOM_SUMMARY_KEYS, room_map if isinstance(room_map, Mapping) else {})
            )

    heat_stats: list[dict[str, str]] = [
        {
            "entity": _statistic_id(site_id, _METRIC_HEAT_SPACE),
            "name": "Space heating (site)",
        },
        {
            "entity": _statistic_id(site_id, _METRIC_HEAT_UNALLOCATED),
            "name": "Unallocated",
        },
    ]
    temp_stats: list[dict[str, str]] = []
    for room in rooms:
        room_id = str(room.get("room_id") or room.get("id") or "")
        if not room_id:
            continue
        name = str(room.get("name") or room_id)
        heat_stats.append(
            {
                "entity": _statistic_id(site_id, _room_heat_metric(room_id)),
                "name": name,
            }
        )
        temp_stats.append(
            {
                "entity": _statistic_id(site_id, _room_t_mean_metric(room_id)),
                "name": f"{name} temperature",
            }
        )
    right: list[dict[str, Any]] = [
        {
            "type": "statistics-graph",
            "title": "Room heat and unallocated per day (kWh)",
            "chart_type": "bar",
            "period": "day",
            "days_to_show": 60,
            "stat_types": ["change"],
            "entities": heat_stats,
        }
    ]
    if temp_stats:
        right.append(
            {
                "type": "statistics-graph",
                "title": "Room temperature per day (°C)",
                "chart_type": "line",
                "period": "day",
                "days_to_show": 60,
                "stat_types": ["mean"],
                "entities": temp_stats,
            }
        )
    return [
        {"type": "vertical-stack", "cards": left},
        {"type": "vertical-stack", "cards": right},
    ]
