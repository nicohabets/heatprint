"""First-run defaults: reuse the HA home, do not ask again.

Home Assistant-free so defaults can be unit-tested. Keys stay in lockstep
with ``const.py``. Weather, methods, DHW and history use the same values
the old wizard would have stored; the config flow only confirms them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CONF_BACKFILL_YEARS = "backfill_years"
CONF_CLASSIC_BASE_TEMP = "classic_base_temp"
CONF_CLASSIC_HEATING_LIMIT = "classic_heating_limit"
CONF_CLASSIC_WEIGHTED = "classic_weighted"
CONF_CLIMATOLOGY_YEARS = "climatology_years"
CONF_DHW_OVERRIDE = "dhw_override"
CONF_FALLBACK = "fallback"
CONF_HOUSE_FIT_WIND = "house_fit_wind"
CONF_IMPORT_NOW = "import_now"
CONF_METHODS_ENABLED = "enabled"
CONF_METHODS_PRIMARY = "primary"
CONF_OUTPUT_W_PER_M2_ELECTRIC = "output_w_per_m2_electric"
CONF_OUTPUT_W_PER_M2_OTHER = "output_w_per_m2_other"
CONF_OUTPUT_W_PER_M2_RADIATOR = "output_w_per_m2_radiator"
CONF_OUTPUT_W_PER_M2_UNDERFLOOR = "output_w_per_m2_underfloor"
CONF_PBL_INCLUDE_SUN = "pbl_include_sun"
CONF_PBL_PARAMETER_SET = "pbl_parameter_set"
CONF_PBL_WIND_MODE = "pbl_wind_mode"
CONF_PROVIDER = "provider"
CONF_ROOMS_ALLOCATION = "allocation_enabled"
CONF_ROOMS_AUTO_SYNC = "auto_sync"
CONF_ROOMS_EXCLUDE_AREAS = "exclude_area_ids"
CONF_ROOMS_MIN_FIT_DAYS = "min_room_fit_days"
CONF_SEASON_START = "season_start"
CONF_STATION_ID = "station_id"
CONF_SUMMER_END = "summer_end"
CONF_SUMMER_START = "summer_start"
DEFAULT_BACKFILL_YEARS = 3
DEFAULT_CLASSIC_BASE_TEMP = 18.0
DEFAULT_CLASSIC_HEATING_LIMIT = 18.0
DEFAULT_CLIMATOLOGY_YEARS = 20
DEFAULT_KNMI_STATION = "260"
DEFAULT_METHOD_PRIMARY = "house"
DEFAULT_METHODS_ENABLED = ["classic", "pbl", "house"]
DEFAULT_OUTPUT_W_PER_M2 = {
    "radiator": 70.0,
    "underfloor": 50.0,
    "electric": 100.0,
    "other": 70.0,
}
DEFAULT_ROOMS_ALLOCATION = True
DEFAULT_ROOMS_AUTO_SYNC = True
DEFAULT_ROOMS_MIN_FIT_DAYS = 30
DEFAULT_SUMMER_END = "08-31"
DEFAULT_SUMMER_START = "06-01"
DHW_OVERRIDE_KEEP = "keep"
FALLBACK_NONE = "none"
OPT_DHW = "dhw"
OPT_HISTORY = "history"
OPT_METHODS = "methods"
OPT_ROOMS = "rooms"
PROVIDER_KNMI = "knmi"
PROVIDER_OPEN_METEO = "open_meteo"
SEASON_START_OCTOBER = "october"


def default_weather_config(
    country: str,
    *,
    nearest_station_id: str | None = None,
) -> dict[str, str]:
    """Pick KNMI (NL) or Open-Meteo from the HA home country. Never asked."""
    if country == "NL":
        return {
            CONF_PROVIDER: PROVIDER_KNMI,
            CONF_STATION_ID: nearest_station_id or DEFAULT_KNMI_STATION,
            CONF_FALLBACK: PROVIDER_OPEN_METEO,
        }
    return {CONF_PROVIDER: PROVIDER_OPEN_METEO, CONF_FALLBACK: FALLBACK_NONE}


def default_rooms_options(
    current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rooms options with auto-sync on and an empty exclude list."""
    values = dict(current or {})
    values.setdefault(CONF_ROOMS_ALLOCATION, DEFAULT_ROOMS_ALLOCATION)
    values.setdefault(CONF_ROOMS_MIN_FIT_DAYS, DEFAULT_ROOMS_MIN_FIT_DAYS)
    values.setdefault(CONF_ROOMS_AUTO_SYNC, DEFAULT_ROOMS_AUTO_SYNC)
    values.setdefault(CONF_ROOMS_EXCLUDE_AREAS, [])
    values.setdefault(CONF_OUTPUT_W_PER_M2_RADIATOR, DEFAULT_OUTPUT_W_PER_M2["radiator"])
    values.setdefault(CONF_OUTPUT_W_PER_M2_UNDERFLOOR, DEFAULT_OUTPUT_W_PER_M2["underfloor"])
    values.setdefault(CONF_OUTPUT_W_PER_M2_ELECTRIC, DEFAULT_OUTPUT_W_PER_M2["electric"])
    values.setdefault(CONF_OUTPUT_W_PER_M2_OTHER, DEFAULT_OUTPUT_W_PER_M2["other"])
    return values


def default_entry_options() -> dict[str, Any]:
    """Return options the old wizard would have stored on confirm."""
    return {
        OPT_METHODS: {
            CONF_SEASON_START: SEASON_START_OCTOBER,
            CONF_METHODS_ENABLED: list(DEFAULT_METHODS_ENABLED),
            CONF_METHODS_PRIMARY: DEFAULT_METHOD_PRIMARY,
            CONF_CLASSIC_WEIGHTED: True,
            CONF_CLASSIC_BASE_TEMP: DEFAULT_CLASSIC_BASE_TEMP,
            CONF_CLASSIC_HEATING_LIMIT: DEFAULT_CLASSIC_HEATING_LIMIT,
            CONF_PBL_PARAMETER_SET: "practical",
            CONF_PBL_WIND_MODE: "linear",
            CONF_PBL_INCLUDE_SUN: False,
            CONF_HOUSE_FIT_WIND: True,
        },
        OPT_DHW: {
            CONF_DHW_OVERRIDE: DHW_OVERRIDE_KEEP,
            CONF_SUMMER_START: DEFAULT_SUMMER_START,
            CONF_SUMMER_END: DEFAULT_SUMMER_END,
        },
        OPT_HISTORY: {
            CONF_BACKFILL_YEARS: DEFAULT_BACKFILL_YEARS,
            CONF_CLIMATOLOGY_YEARS: DEFAULT_CLIMATOLOGY_YEARS,
            CONF_IMPORT_NOW: False,
        },
        OPT_ROOMS: default_rooms_options(),
    }
