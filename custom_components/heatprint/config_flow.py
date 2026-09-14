"""Config flow for Heatprint (CONFIG_FLOW.md).

First-run is a single confirm of the Home Assistant home (location, weather,
meters and heated areas are taken from HA). Generators and rooms become
subentries. The options flow manages methods, DHW, history, CSV import,
pricing, mindergas, rooms sync and advanced parameters. Reconfigure changes
location and weather source. A leftover multi-step wizard (situation →
generators → DHW → methods → history → summary) still exists in this module
but is not reached from ``async_step_user``.
"""

from __future__ import annotations

import logging
import math
import re
import zoneinfo
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    BooleanSelector,
    CountrySelector,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    FileSelector,
    FileSelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    ATTR_CSV,
    ATTR_DATE_COLUMN,
    ATTR_PATH,
    ATTR_READING_COLUMN,
    CONF_AREA_ID,
    CONF_BACKFILL_YEARS,
    CONF_CATEGORY,
    CONF_CLASSIC_BASE_TEMP,
    CONF_CLASSIC_HEATING_LIMIT,
    CONF_CLASSIC_WEIGHTED,
    CONF_CLIMATOLOGY_YEARS,
    CONF_CO2_ENTITY,
    CONF_CO2_FACTOR,
    CONF_CONVERSION_MODE,
    CONF_COP,
    CONF_COUNTRY,
    CONF_DATE,
    CONF_DEMAND_ENTITY,
    CONF_DEMAND_KIND,
    CONF_DHW_ELECTRIC_ENTITY,
    CONF_DHW_ENTITY,
    CONF_DHW_FIXED_PER_DAY,
    CONF_DHW_MODE,
    CONF_DHW_OVERRIDE,
    CONF_DISTRICT_CO2_FACTOR,
    CONF_EFFICIENCY,
    CONF_ELECTRIC_CO2_FACTOR,
    CONF_ELECTRIC_ENTITY,
    CONF_EMITTER_KIND,
    CONF_ENABLED,
    CONF_ENERGY_ENTITY,
    CONF_FACTOR,
    CONF_FALLBACK,
    CONF_FLOOR_AREA_M2,
    CONF_GAS_CO2_FACTOR,
    CONF_GENERATOR_ID,
    CONF_HA_ENTITIES,
    CONF_HEATING_VALUE,
    CONF_HEATING_VALUE_CUSTOM,
    CONF_HOUSE_FIT_WIND,
    CONF_IMPORT_NOW,
    CONF_KIND,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_MEASURE_ID,
    CONF_METHODS_ENABLED,
    CONF_METHODS_PRIMARY,
    CONF_MIN_FIT_DAYS,
    CONF_MINDERGAS_DAILY_PUSH,
    CONF_MINDERGAS_GENERATOR,
    CONF_MINDERGAS_TOKEN,
    CONF_NAME,
    CONF_NOTES,
    CONF_OUTLIER_THRESHOLD,
    CONF_OUTPUT_W_PER_M2_ELECTRIC,
    CONF_OUTPUT_W_PER_M2_OTHER,
    CONF_OUTPUT_W_PER_M2_RADIATOR,
    CONF_OUTPUT_W_PER_M2_UNDERFLOOR,
    CONF_PBL_INCLUDE_SUN,
    CONF_PBL_PARAMETER_SET,
    CONF_PBL_RER_SHOULDER,
    CONF_PBL_RER_SUMMER,
    CONF_PBL_RER_TRANSITION,
    CONF_PBL_RER_WINTER,
    CONF_PBL_TOP,
    CONF_PBL_TST_SHOULDER,
    CONF_PBL_TST_SUMMER,
    CONF_PBL_TST_TRANSITION,
    CONF_PBL_TST_WINTER,
    CONF_PBL_WIND_MODE,
    CONF_PBL_WIND_SQRT_COEF,
    CONF_PRICE_ENTITY,
    CONF_PROVIDER,
    CONF_RADIATION_ENTITY,
    CONF_RATED_OUTPUT_W,
    CONF_RECOMPUTE_FROM,
    CONF_ROLE,
    CONF_ROOM_ID,
    CONF_ROOM_TEMPERATURE_ENTITY,
    CONF_ROOMS_ALLOCATION,
    CONF_ROOMS_AUTO_SYNC,
    CONF_ROOMS_EXCLUDE_AREAS,
    CONF_ROOMS_MIN_FIT_DAYS,
    CONF_ROOMS_SYNC_NOW,
    CONF_SCOP,
    CONF_SEASON_START,
    CONF_SITE_ID,
    CONF_SITUATION,
    CONF_STATION_ID,
    CONF_SUMMER_END,
    CONF_SUMMER_START,
    CONF_TEMPERATURE_ENTITY,
    CONF_THERMAL_ENTITY,
    CONF_TIMEZONE,
    CONF_UNIT,
    CONF_VOLUME_M3,
    CONF_WEATHER,
    CONF_WIND_ENTITY,
    CONVERSION_AUTO,
    DEFAULT_BACKFILL_YEARS,
    DEFAULT_CLASSIC_BASE_TEMP,
    DEFAULT_CLASSIC_HEATING_LIMIT,
    DEFAULT_CLIMATOLOGY_YEARS,
    DEFAULT_COP_AIR_TO_AIR,
    DEFAULT_DISTRICT_CO2_KG_PER_KWH,
    DEFAULT_DISTRICT_EFFICIENCY,
    DEFAULT_ELECTRIC_CO2_KG_PER_KWH,
    DEFAULT_FACTOR,
    DEFAULT_GAS_CO2_KG_PER_M3,
    DEFAULT_GAS_EFFICIENCY,
    DEFAULT_KNMI_STATION,
    DEFAULT_METHOD_PRIMARY,
    DEFAULT_METHODS_ENABLED,
    DEFAULT_MIN_FIT_DAYS,
    DEFAULT_OUTLIER_THRESHOLD,
    DEFAULT_OUTPUT_W_PER_M2,
    DEFAULT_PBL_RER,
    DEFAULT_PBL_TOP,
    DEFAULT_PBL_TST,
    DEFAULT_PBL_WIND_SQRT_COEF,
    DEFAULT_ROOMS_ALLOCATION,
    DEFAULT_ROOMS_AUTO_SYNC,
    DEFAULT_ROOMS_MIN_FIT_DAYS,
    DEFAULT_SCOP,
    DEFAULT_SUMMER_END,
    DEFAULT_SUMMER_START,
    DEMAND_KIND_BINARY,
    DEMAND_KIND_METERED,
    DEMAND_KIND_PERCENTAGE,
    DEMAND_KIND_VALVE,
    DEMAND_KINDS,
    DHW_BASELINE,
    DHW_MEASURED,
    DHW_MODES,
    DHW_OVERRIDE_KEEP,
    DHW_OVERRIDE_OPTIONS,
    DOMAIN,
    EMITTER_KIND_RADIATOR,
    EMITTER_KINDS,
    ENERGY_UNITS,
    FALLBACKS,
    GAS_UNITS,
    GENERATOR_KINDS,
    GJ_TO_KWH,
    HEAT_PUMP_CONVERSION_MODES,
    HEAT_UNITS,
    HEATING_VALUE_HS,
    HEATING_VALUE_OPTIONS,
    IMPORT_UNITS,
    KIND_AIR_TO_AIR,
    KIND_DEFAULTS,
    KIND_DISTRICT_HEAT,
    KIND_ELECTRIC_HEATER,
    KIND_GAS_BOILER,
    KIND_HEAT_PUMP,
    KIND_OTHER,
    KNMI_STATIONS,
    MEASURE_CATEGORIES,
    METHODS,
    OPT_ADVANCED,
    OPT_DHW,
    OPT_HISTORY,
    OPT_IMPORT,
    OPT_INTEGRATIONS,
    OPT_METHODS,
    OPT_PRICING,
    OPT_ROOMS,
    OPT_SYNC_ROOMS,
    PBL_PARAMETER_SETS,
    PBL_WIND_MODES,
    PROVIDER_HA_SENSORS,
    PROVIDER_KNMI,
    PROVIDER_OPEN_METEO,
    PROVIDERS_INTL,
    PROVIDERS_NL,
    ROLE_BOTH,
    ROLES,
    SEASON_START_OCTOBER,
    SEASON_STARTS,
    SECTION_ADVANCED,
    SECTION_CONVERSION,
    SECTION_DHW,
    SECTION_FIT,
    SECTION_PBL,
    SECTION_PRICING,
    SITUATION_DRAFTS,
    SITUATIONS,
    SUBENTRY_TYPE_GENERATOR,
    SUBENTRY_TYPE_MEASURE,
    SUBENTRY_TYPE_ROOM,
    UNIT_GJ,
    UNIT_KWH,
    UNIT_M3,
)
from .core_api import (
    WeatherCannotConnect,
    WeatherNoData,
    async_test_weather,
    inspect_readings_csv,
    weather_signature_from_data,
)
from .first_run import default_entry_options, default_weather_config
from .room_discovery import discover_rooms_from_hass
from .room_sync import discovered_to_subentry_payloads, sync_rooms_from_hass
from .site_defaults import site_defaults_from_hass

_LOGGER = logging.getLogger(__name__)

STATE_CLASS_CUMULATIVE = {"total", "total_increasing"}
MONTH_DAY_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
HEAT_PUMP_NAME_TOKENS = {"hp", "wp"}
# Name fragments that suggest a heat pump sensor. The Dutch "warmtepomp" (and the "wp"
# token above) is intentional: it matches the entity names of Dutch installations.
HEAT_PUMP_NAME_PARTS = ("warmtepomp", "heat pump", "heatpump")

_TIMEZONES: list[str] | None = None


def _load_timezones() -> list[str]:
    """Return all zoneinfo time zones sorted (blocking, run in executor)."""
    return sorted(zoneinfo.available_timezones())


async def _async_timezones(hass: HomeAssistant) -> list[str]:
    """Return the cached list of time zones."""
    global _TIMEZONES  # noqa: PLW0603
    if _TIMEZONES is None:
        _TIMEZONES = await hass.async_add_executor_job(_load_timezones)
    return _TIMEZONES


# --------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------


def _select(options: list[str], translation_key: str, *, multiple: bool = False) -> SelectSelector:
    """Return a dropdown select selector with translated option labels."""
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key=translation_key,
            mode=SelectSelectorMode.DROPDOWN,
            multiple=multiple,
        )
    )


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    """Return a number box selector."""
    config: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "step": step,
        "mode": NumberSelectorMode.BOX,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(NumberSelectorConfig(**config))


def _entity(device_class: list[str] | None = None) -> EntitySelector:
    """Return a sensor entity selector, optionally filtered on device class."""
    config: dict[str, Any] = {"domain": "sensor"}
    if device_class:
        config["device_class"] = device_class
    return EntitySelector(EntitySelectorConfig(**config))


def _suggested(value: Any) -> dict[str, Any]:
    """Return the description dict prefilling a field with a suggested value."""
    return {"suggested_value": value} if value is not None else {}


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres."""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _station_options(latitude: float, longitude: float) -> tuple[list[SelectOptionDict], str]:
    """Return KNMI station options sorted by distance and the nearest station id."""
    ranked = sorted(
        (
            (_distance_km(latitude, longitude, lat, lon), station_id, name)
            for station_id, (name, lat, lon) in KNMI_STATIONS.items()
        ),
        key=lambda item: item[0],
    )
    options = [
        SelectOptionDict(value=station_id, label=f"{name} ({station_id}) - {distance:.0f} km")
        for distance, station_id, name in ranked
    ]
    nearest = ranked[0][1] if ranked else DEFAULT_KNMI_STATION
    return options, nearest


def _unique_slug(name: str, existing: set[str], fallback: str) -> str:
    """Return a slug derived from name that is not in existing."""
    base = slugify(name) or fallback
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _detect_candidates(hass: HomeAssistant) -> tuple[list[str], list[str]]:
    """Suggest gas and heat pump sensors (CONFIG_FLOW step 3 autodetection)."""
    gas: list[str] = []
    heat_pump: list[str] = []
    for state in hass.states.async_all("sensor"):
        attrs = state.attributes
        device_class = attrs.get("device_class")
        state_class = attrs.get("state_class")
        if device_class == "gas" and state_class == "total_increasing":
            gas.append(state.entity_id)
        elif device_class == "energy" and state_class in STATE_CLASS_CUMULATIVE:
            haystack = f"{state.name} {state.entity_id}".lower()
            tokens = set(re.split(r"[^a-z0-9]+", haystack))
            if tokens & HEAT_PUMP_NAME_TOKENS or any(
                part in haystack for part in HEAT_PUMP_NAME_PARTS
            ):
                heat_pump.append(state.entity_id)
    return sorted(gas), sorted(heat_pump)


@callback
def _validate_cumulative_entity(
    hass: HomeAssistant, entity_id: str, expected_units: frozenset[str]
) -> str | None:
    """Return an error key when the entity is not a usable cumulative meter."""
    state = hass.states.get(entity_id)
    if state is None:
        return "entity_not_found"
    if state.attributes.get("state_class") not in STATE_CLASS_CUMULATIVE:
        return "entity_not_cumulative"
    if expected_units and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in expected_units:
        return "unit_mismatch"
    return None


@callback
def _validate_measurement_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """Return an error key when a weather sensor cannot produce long-term statistics."""
    state = hass.states.get(entity_id)
    if state is None:
        return "entity_not_found"
    if state.attributes.get("state_class") != "measurement":
        return "entity_no_statistics"
    return None


@callback
def _carrier_unit_of(hass: HomeAssistant, entity_id: str | None, default: str) -> str:
    """Derive the carrier unit (m3 / kwh / gj) from the entity's unit of measurement."""
    if not entity_id or (state := hass.states.get(entity_id)) is None:
        return default
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if unit in GAS_UNITS:
        return UNIT_M3
    if unit in ("GJ", "MJ"):
        return UNIT_GJ
    if unit in ENERGY_UNITS:
        return UNIT_KWH
    return default


async def _async_validate_weather(
    hass: HomeAssistant, weather: Mapping[str, Any], latitude: float, longitude: float
) -> str | None:
    """Run a 7-day test fetch; return an error key on failure."""
    try:
        await async_test_weather(async_get_clientsession(hass), weather, latitude, longitude)
    except WeatherNoData:
        return "no_data_for_station"
    except WeatherCannotConnect:
        return "cannot_connect"
    except Exception:  # noqa: BLE001 - core exception types are reconciled later
        return "cannot_connect"
    return None


# --------------------------------------------------------------------------------
# Shared schemas (config flow, subentry flow, options flow)
# --------------------------------------------------------------------------------


def generator_base_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for CONFIG_FLOW 4.1: name, kind and role."""
    kind = defaults.get(CONF_KIND, KIND_GAS_BOILER)
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, KIND_DEFAULTS[kind].name)
            ): TextSelector(),
            vol.Required(CONF_KIND, default=kind): _select(GENERATOR_KINDS, "generator_kind"),
            vol.Required(
                CONF_ROLE, default=defaults.get(CONF_ROLE, KIND_DEFAULTS[kind].role)
            ): _select(ROLES, "generator_role"),
        }
    )


def generator_details_schema(kind: str, role: str, defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for CONFIG_FLOW 4.2-4.5: sensors, conversion, DHW and pricing sections."""
    fields: dict[Any, Any] = {}
    if kind == KIND_HEAT_PUMP:
        fields[
            vol.Optional(
                CONF_THERMAL_ENTITY, description=_suggested(defaults.get(CONF_THERMAL_ENTITY))
            )
        ] = _entity(["energy"])
        fields[
            vol.Optional(
                CONF_ELECTRIC_ENTITY, description=_suggested(defaults.get(CONF_ELECTRIC_ENTITY))
            )
        ] = _entity(["energy"])
        if role == ROLE_BOTH:
            fields[
                vol.Optional(CONF_DHW_ENTITY, description=_suggested(defaults.get(CONF_DHW_ENTITY)))
            ] = _entity(["energy"])
            fields[
                vol.Optional(
                    CONF_DHW_ELECTRIC_ENTITY,
                    description=_suggested(defaults.get(CONF_DHW_ELECTRIC_ENTITY)),
                )
            ] = _entity(["energy"])
    else:
        device_class: list[str] | None
        if kind == KIND_GAS_BOILER:
            device_class = ["gas"]
        elif kind == KIND_OTHER:
            device_class = None
        else:
            device_class = ["energy"]
        fields[
            vol.Required(
                CONF_ENERGY_ENTITY, description=_suggested(defaults.get(CONF_ENERGY_ENTITY))
            )
        ] = _entity(device_class)
        if kind in (KIND_GAS_BOILER, KIND_DISTRICT_HEAT) and role == ROLE_BOTH:
            fields[
                vol.Optional(CONF_DHW_ENTITY, description=_suggested(defaults.get(CONF_DHW_ENTITY)))
            ] = _entity(["energy"])

    conversion: dict[Any, Any] = {}
    if kind == KIND_GAS_BOILER:
        conversion[
            vol.Required(
                CONF_HEATING_VALUE, default=defaults.get(CONF_HEATING_VALUE, HEATING_VALUE_HS)
            )
        ] = _select(HEATING_VALUE_OPTIONS, "heating_value")
        conversion[
            vol.Optional(
                CONF_HEATING_VALUE_CUSTOM,
                description=_suggested(defaults.get(CONF_HEATING_VALUE_CUSTOM)),
            )
        ] = _number(5.0, 15.0, 0.001, "kWh/m³")
        conversion[
            vol.Required(
                CONF_EFFICIENCY, default=defaults.get(CONF_EFFICIENCY, DEFAULT_GAS_EFFICIENCY)
            )
        ] = _number(0.5, 1.1, 0.01)
    elif kind == KIND_HEAT_PUMP:
        conversion[
            vol.Required(
                CONF_CONVERSION_MODE, default=defaults.get(CONF_CONVERSION_MODE, CONVERSION_AUTO)
            )
        ] = _select(HEAT_PUMP_CONVERSION_MODES, "conversion_mode")
        conversion[vol.Required(CONF_SCOP, default=defaults.get(CONF_SCOP, DEFAULT_SCOP))] = (
            _number(1.0, 7.0, 0.1)
        )
    elif kind == KIND_AIR_TO_AIR:
        conversion[
            vol.Required(CONF_COP, default=defaults.get(CONF_COP, DEFAULT_COP_AIR_TO_AIR))
        ] = _number(1.0, 7.0, 0.1)
    elif kind == KIND_DISTRICT_HEAT:
        conversion[
            vol.Required(
                CONF_EFFICIENCY, default=defaults.get(CONF_EFFICIENCY, DEFAULT_DISTRICT_EFFICIENCY)
            )
        ] = _number(0.5, 1.1, 0.01)
    elif kind == KIND_OTHER:
        conversion[vol.Required(CONF_FACTOR, default=defaults.get(CONF_FACTOR, DEFAULT_FACTOR))] = (
            _number(0.001, 1000.0, 0.001)
        )
    if conversion:
        fields[vol.Required(SECTION_CONVERSION)] = section(
            vol.Schema(conversion), {"collapsed": False}
        )

    if role == ROLE_BOTH:
        dhw_default = defaults.get(CONF_DHW_MODE) or (
            DHW_MEASURED if defaults.get(CONF_DHW_ENTITY) else DHW_BASELINE
        )
        dhw = {
            vol.Required(CONF_DHW_MODE, default=dhw_default): _select(DHW_MODES, "dhw_mode"),
            vol.Optional(
                CONF_DHW_FIXED_PER_DAY, description=_suggested(defaults.get(CONF_DHW_FIXED_PER_DAY))
            ): _number(0.0, 1000.0, 0.01),
        }
        fields[vol.Required(SECTION_DHW)] = section(vol.Schema(dhw), {"collapsed": False})

    pricing = {
        vol.Optional(
            CONF_PRICE_ENTITY, description=_suggested(defaults.get(CONF_PRICE_ENTITY))
        ): _entity(),
        vol.Required(
            CONF_CO2_FACTOR, default=defaults.get(CONF_CO2_FACTOR, KIND_DEFAULTS[kind].co2_factor)
        ): _number(0.0, 10.0, 0.001),
    }
    fields[vol.Required(SECTION_PRICING)] = section(vol.Schema(pricing), {"collapsed": True})
    return vol.Schema(fields)


def flatten_sections(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Merge section dicts of a submitted form into one flat dict."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in (
            SECTION_CONVERSION,
            SECTION_DHW,
            SECTION_PRICING,
            SECTION_ADVANCED,
            SECTION_PBL,
            SECTION_FIT,
        ) and isinstance(value, Mapping):
            flat.update(value)
        else:
            flat[key] = value
    return flat


@callback
def validate_generator_details(
    hass: HomeAssistant, kind: str, role: str, data: Mapping[str, Any]
) -> dict[str, str]:
    """Validate the sensors of CONFIG_FLOW 4.2; return errors per field."""
    errors: dict[str, str] = {}
    if kind == KIND_HEAT_PUMP:
        if not data.get(CONF_THERMAL_ENTITY) and not data.get(CONF_ELECTRIC_ENTITY):
            errors["base"] = "missing_thermal_or_electric"
        for key, units in (
            (CONF_THERMAL_ENTITY, HEAT_UNITS),
            (CONF_ELECTRIC_ENTITY, ENERGY_UNITS),
            (CONF_DHW_ENTITY, HEAT_UNITS),
            (CONF_DHW_ELECTRIC_ENTITY, ENERGY_UNITS),
        ):
            if data.get(key) and (error := _validate_cumulative_entity(hass, data[key], units)):
                errors[key] = error
        return errors
    if kind == KIND_GAS_BOILER:
        units = GAS_UNITS
    elif kind == KIND_DISTRICT_HEAT:
        units = HEAT_UNITS
    elif kind == KIND_OTHER:
        units = frozenset()
    else:
        units = ENERGY_UNITS
    if not data.get(CONF_ENERGY_ENTITY):
        errors[CONF_ENERGY_ENTITY] = "entity_not_found"
    elif error := _validate_cumulative_entity(hass, data[CONF_ENERGY_ENTITY], units):
        errors[CONF_ENERGY_ENTITY] = error
    if data.get(CONF_DHW_ENTITY) and (
        error := _validate_cumulative_entity(hass, data[CONF_DHW_ENTITY], HEAT_UNITS)
    ):
        errors[CONF_DHW_ENTITY] = error
    return errors


@callback
def normalize_generator(
    hass: HomeAssistant,
    base: Mapping[str, Any],
    details: Mapping[str, Any],
    existing_ids: set[str],
    keep_id: str | None = None,
) -> dict[str, Any]:
    """Build the flat generator subentry data from the two forms."""
    kind = base[CONF_KIND]
    role = base[CONF_ROLE]
    name = str(base[CONF_NAME]).strip() or KIND_DEFAULTS[kind].name
    generator_id = keep_id or _unique_slug(name, existing_ids, kind)
    data: dict[str, Any] = {
        CONF_GENERATOR_ID: generator_id,
        CONF_NAME: name,
        CONF_KIND: kind,
        CONF_ROLE: role,
    }
    for key in (
        CONF_ENERGY_ENTITY,
        CONF_THERMAL_ENTITY,
        CONF_ELECTRIC_ENTITY,
        CONF_DHW_ENTITY,
        CONF_DHW_ELECTRIC_ENTITY,
        CONF_PRICE_ENTITY,
    ):
        if details.get(key):
            data[key] = details[key]
    if kind == KIND_HEAT_PUMP:
        # For heat pumps the electric meter is the carrier (DATA_MODEL 1.3).
        if details.get(CONF_ELECTRIC_ENTITY):
            data[CONF_ENERGY_ENTITY] = details[CONF_ELECTRIC_ENTITY]
        data[CONF_UNIT] = UNIT_KWH
        data[CONF_CONVERSION_MODE] = details.get(CONF_CONVERSION_MODE, CONVERSION_AUTO)
        data[CONF_SCOP] = float(details.get(CONF_SCOP, DEFAULT_SCOP))
    else:
        data[CONF_UNIT] = _carrier_unit_of(
            hass, details.get(CONF_ENERGY_ENTITY), UNIT_M3 if kind == KIND_GAS_BOILER else UNIT_KWH
        )
        data[CONF_CONVERSION_MODE] = KIND_DEFAULTS[kind].conversion_mode
    if kind == KIND_GAS_BOILER:
        data[CONF_HEATING_VALUE] = details.get(CONF_HEATING_VALUE, HEATING_VALUE_HS)
        if details.get(CONF_HEATING_VALUE_CUSTOM) is not None:
            data[CONF_HEATING_VALUE_CUSTOM] = float(details[CONF_HEATING_VALUE_CUSTOM])
        data[CONF_EFFICIENCY] = float(details.get(CONF_EFFICIENCY, DEFAULT_GAS_EFFICIENCY))
    elif kind == KIND_AIR_TO_AIR:
        data[CONF_COP] = float(details.get(CONF_COP, DEFAULT_COP_AIR_TO_AIR))
    elif kind == KIND_DISTRICT_HEAT:
        data[CONF_EFFICIENCY] = float(details.get(CONF_EFFICIENCY, DEFAULT_DISTRICT_EFFICIENCY))
    elif kind in (KIND_OTHER, KIND_ELECTRIC_HEATER):
        data[CONF_FACTOR] = float(details.get(CONF_FACTOR, DEFAULT_FACTOR))
    if role == ROLE_BOTH:
        data[CONF_DHW_MODE] = details.get(CONF_DHW_MODE, DHW_BASELINE)
        if details.get(CONF_DHW_FIXED_PER_DAY) is not None:
            data[CONF_DHW_FIXED_PER_DAY] = float(details[CONF_DHW_FIXED_PER_DAY])
    data[CONF_CO2_FACTOR] = float(details.get(CONF_CO2_FACTOR, KIND_DEFAULTS[kind].co2_factor))
    return data


def methods_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for CONFIG_FLOW step 6 (also used by the options flow)."""
    advanced = {
        vol.Required(
            CONF_CLASSIC_BASE_TEMP,
            default=defaults.get(CONF_CLASSIC_BASE_TEMP, DEFAULT_CLASSIC_BASE_TEMP),
        ): _number(5.0, 25.0, 0.1, "°C"),
        vol.Required(
            CONF_CLASSIC_HEATING_LIMIT,
            default=defaults.get(CONF_CLASSIC_HEATING_LIMIT, DEFAULT_CLASSIC_HEATING_LIMIT),
        ): _number(5.0, 25.0, 0.1, "°C"),
        vol.Required(
            CONF_PBL_PARAMETER_SET, default=defaults.get(CONF_PBL_PARAMETER_SET, "practical")
        ): _select(PBL_PARAMETER_SETS, "pbl_parameter_set"),
        vol.Required(
            CONF_PBL_WIND_MODE, default=defaults.get(CONF_PBL_WIND_MODE, "linear")
        ): _select(PBL_WIND_MODES, "pbl_wind_mode"),
        vol.Required(
            CONF_PBL_INCLUDE_SUN, default=defaults.get(CONF_PBL_INCLUDE_SUN, False)
        ): BooleanSelector(),
        vol.Required(
            CONF_HOUSE_FIT_WIND, default=defaults.get(CONF_HOUSE_FIT_WIND, True)
        ): BooleanSelector(),
    }
    return vol.Schema(
        {
            vol.Required(
                CONF_SEASON_START, default=defaults.get(CONF_SEASON_START, SEASON_START_OCTOBER)
            ): _select(SEASON_STARTS, "season_start"),
            vol.Required(
                CONF_METHODS_ENABLED,
                default=list(defaults.get(CONF_METHODS_ENABLED, DEFAULT_METHODS_ENABLED)),
            ): _select(METHODS, "method", multiple=True),
            vol.Required(
                CONF_METHODS_PRIMARY,
                default=defaults.get(CONF_METHODS_PRIMARY, DEFAULT_METHOD_PRIMARY),
            ): _select(METHODS, "method"),
            vol.Required(
                CONF_CLASSIC_WEIGHTED, default=defaults.get(CONF_CLASSIC_WEIGHTED, True)
            ): BooleanSelector(),
            vol.Required(SECTION_ADVANCED): section(vol.Schema(advanced), {"collapsed": True}),
        }
    )


def dhw_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for CONFIG_FLOW step 5 (site-level DHW defaults)."""
    return vol.Schema(
        {
            vol.Required(
                CONF_DHW_OVERRIDE, default=defaults.get(CONF_DHW_OVERRIDE, DHW_OVERRIDE_KEEP)
            ): _select(DHW_OVERRIDE_OPTIONS, "dhw_override"),
            vol.Required(
                CONF_SUMMER_START, default=defaults.get(CONF_SUMMER_START, DEFAULT_SUMMER_START)
            ): TextSelector(),
            vol.Required(
                CONF_SUMMER_END, default=defaults.get(CONF_SUMMER_END, DEFAULT_SUMMER_END)
            ): TextSelector(),
        }
    )


def history_schema(defaults: Mapping[str, Any], *, options: bool) -> vol.Schema:
    """Schema for CONFIG_FLOW step 7; the options variant adds "recompute from"."""
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_BACKFILL_YEARS, default=defaults.get(CONF_BACKFILL_YEARS, DEFAULT_BACKFILL_YEARS)
        ): _number(0, 10, 1),
        vol.Required(
            CONF_CLIMATOLOGY_YEARS,
            default=defaults.get(CONF_CLIMATOLOGY_YEARS, DEFAULT_CLIMATOLOGY_YEARS),
        ): _number(10, 30, 1),
    }
    if options:
        fields[vol.Optional(CONF_RECOMPUTE_FROM)] = DateSelector()
    else:
        fields[vol.Required(CONF_IMPORT_NOW, default=False)] = BooleanSelector()
    return vol.Schema(fields)


def _validate_month_day(value: str) -> bool:
    """Return True when value is a valid MM-DD string (a real day; 02-29 is accepted)."""
    match = MONTH_DAY_RE.match(value.strip())
    if not match:
        return False
    try:
        # A leap year so that 02-29 passes; the core clamps it in common years.
        date(2024, int(match.group(1)), int(match.group(2)))
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------------
# Main config flow
# --------------------------------------------------------------------------------


class HeatprintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Heatprint config flow (one entry per site)."""

    VERSION = 1
    MINOR_VERSION = 0

    def __init__(self) -> None:
        """Initialise flow state."""
        self._site: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._generators: list[dict[str, Any]] = []
        self._drafts: list[tuple[str, str]] = []
        self._current: dict[str, Any] = {}
        self._reconfigure_confirmed = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HeatprintOptionsFlow:
        """Return the options flow handler."""
        return HeatprintOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry flows for generators and measures."""
        return {
            SUBENTRY_TYPE_GENERATOR: GeneratorSubentryFlowHandler,
            SUBENTRY_TYPE_MEASURE: MeasureSubentryFlowHandler,
            SUBENTRY_TYPE_ROOM: RoomSubentryFlowHandler,
        }

    # --- step 1: confirm HA home (no extra questions) ----------------------------------

    def _auto_weather(self) -> dict[str, Any]:
        """Weather from HA home country/coordinates; never asked on first setup."""
        defaults = site_defaults_from_hass(self.hass)
        nearest = None
        if defaults.country == "NL":
            _, nearest = _station_options(defaults.latitude, defaults.longitude)
        return default_weather_config(defaults.country, nearest_station_id=nearest)

    def _auto_generators(self) -> list[dict[str, Any]]:
        """Create generator drafts from high-confidence HA energy sensors."""
        gas, heat_pump = _detect_candidates(self.hass)
        generators: list[dict[str, Any]] = []
        existing: set[str] = set()
        for entity_id in gas:
            base = {
                CONF_NAME: KIND_DEFAULTS[KIND_GAS_BOILER].name,
                CONF_KIND: KIND_GAS_BOILER,
                CONF_ROLE: ROLE_BOTH,
            }
            details = {CONF_ENERGY_ENTITY: entity_id}
            generator = normalize_generator(self.hass, base, details, existing)
            existing.add(generator[CONF_GENERATOR_ID])
            generators.append(generator)
        for entity_id in heat_pump:
            base = {
                CONF_NAME: KIND_DEFAULTS[KIND_HEAT_PUMP].name,
                CONF_KIND: KIND_HEAT_PUMP,
                CONF_ROLE: ROLE_BOTH,
            }
            details = {CONF_ELECTRIC_ENTITY: entity_id}
            generator = normalize_generator(self.hass, base, details, existing)
            existing.add(generator[CONF_GENERATOR_ID])
            generators.append(generator)
        return generators

    def _weather_label(self, weather: Mapping[str, Any]) -> str:
        """Short weather source for the confirm screen."""
        provider = weather.get(CONF_PROVIDER, "-")
        if provider == PROVIDER_KNMI and weather.get(CONF_STATION_ID):
            station_id = str(weather[CONF_STATION_ID])
            station = KNMI_STATIONS.get(station_id, (station_id, 0, 0))[0]
            return f"KNMI {station} ({station_id})"
        if provider == PROVIDER_OPEN_METEO:
            return "Open-Meteo"
        return str(provider)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Single confirm: reuse HA home, weather, meters and heated areas."""
        defaults = site_defaults_from_hass(self.hass)
        site_id = slugify(defaults.name) or "home"
        weather = self._auto_weather()
        discovery = discover_rooms_from_hass(self.hass)
        generators = self._auto_generators()
        if user_input is not None:
            if any(
                entry.data.get(CONF_SITE_ID) == site_id or entry.title == defaults.name
                for entry in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            await self.async_set_unique_id(site_id)
            self._abort_if_unique_id_configured()
            error = await _async_validate_weather(
                self.hass, weather, defaults.latitude, defaults.longitude
            )
            if error:
                _LOGGER.warning("Weather check at first-run failed (%s); continuing", error)
            site = {
                CONF_SITE_ID: site_id,
                CONF_NAME: defaults.name,
                CONF_LATITUDE: defaults.latitude,
                CONF_LONGITUDE: defaults.longitude,
                CONF_TIMEZONE: defaults.timezone,
                CONF_COUNTRY: defaults.country,
                CONF_WEATHER: weather,
            }
            subentries = [
                ConfigSubentryData(
                    data=generator,
                    subentry_type=SUBENTRY_TYPE_GENERATOR,
                    title=generator[CONF_NAME],
                    unique_id=generator[CONF_GENERATOR_ID],
                )
                for generator in generators
            ]
            for payload in discovered_to_subentry_payloads(discovery.rooms):
                subentries.append(
                    ConfigSubentryData(
                        data=payload["data"],
                        subentry_type=SUBENTRY_TYPE_ROOM,
                        title=payload["title"],
                        unique_id=payload["unique_id"],
                    )
                )
            return self.async_create_entry(
                title=defaults.name,
                data=site,
                options=default_entry_options(),
                subentries=subentries,
            )
        generator_text = (
            ", ".join(
                f"{item[CONF_NAME]} ({item.get(CONF_ENERGY_ENTITY) or item.get(CONF_ELECTRIC_ENTITY)})"
                for item in generators
            )
            or "—"
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": defaults.name,
                "latitude": f"{defaults.latitude:.4f}",
                "longitude": f"{defaults.longitude:.4f}",
                "timezone": defaults.timezone,
                "country": defaults.country or "—",
                "weather": self._weather_label(weather),
                "generators": generator_text,
                "rooms": discovery.room_summary(),
                "skipped": discovery.skipped_summary(),
            },
            last_step=True,
        )

    # --- step 2: weather ---------------------------------------------------------------

    async def _async_step_weather(self) -> ConfigFlowResult:
        """Branch on the country of the site."""
        if self._site.get(CONF_COUNTRY) == "NL":
            return await self.async_step_weather_nl()
        return await self.async_step_weather_intl()

    async def _async_after_weather(self) -> ConfigFlowResult:
        """Continue after a validated weather source."""
        if self.source == SOURCE_RECONFIGURE:
            return await self._async_finish_reconfigure()
        return await self.async_step_situation()

    async def async_step_weather_nl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2a: weather source in the Netherlands (KNMI station)."""
        errors: dict[str, str] = {}
        current = self._site.get(CONF_WEATHER, {})
        options, nearest = _station_options(self._site[CONF_LATITUDE], self._site[CONF_LONGITUDE])
        if user_input is not None:
            weather = {
                CONF_PROVIDER: user_input[CONF_PROVIDER],
                CONF_STATION_ID: user_input[CONF_STATION_ID],
                CONF_FALLBACK: user_input[CONF_FALLBACK],
            }
            if weather[CONF_PROVIDER] == PROVIDER_HA_SENSORS:
                self._site[CONF_WEATHER] = {
                    **weather,
                    CONF_HA_ENTITIES: current.get(CONF_HA_ENTITIES, {}),
                }
                return await self.async_step_weather_sensors()
            error = await _async_validate_weather(
                self.hass, weather, self._site[CONF_LATITUDE], self._site[CONF_LONGITUDE]
            )
            if error:
                errors["base"] = error
            else:
                self._site[CONF_WEATHER] = weather
                return await self._async_after_weather()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER, default=current.get(CONF_PROVIDER, PROVIDER_KNMI)
                ): _select(PROVIDERS_NL, "provider"),
                vol.Required(
                    CONF_STATION_ID, default=current.get(CONF_STATION_ID, nearest)
                ): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(
                    CONF_FALLBACK, default=current.get(CONF_FALLBACK, PROVIDER_OPEN_METEO)
                ): _select(FALLBACKS, "fallback"),
            }
        )
        nearest_name = KNMI_STATIONS[nearest][0]
        return self.async_show_form(
            step_id="weather_nl",
            data_schema=schema,
            errors=errors,
            description_placeholders={"nearest": f"{nearest_name} ({nearest})"},
        )

    async def async_step_weather_intl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b: weather source outside the Netherlands."""
        errors: dict[str, str] = {}
        current = self._site.get(CONF_WEATHER, {})
        if user_input is not None:
            weather = {CONF_PROVIDER: user_input[CONF_PROVIDER], CONF_FALLBACK: "none"}
            if weather[CONF_PROVIDER] == PROVIDER_HA_SENSORS:
                self._site[CONF_WEATHER] = {
                    **weather,
                    CONF_HA_ENTITIES: current.get(CONF_HA_ENTITIES, {}),
                }
                return await self.async_step_weather_sensors()
            error = await _async_validate_weather(
                self.hass, weather, self._site[CONF_LATITUDE], self._site[CONF_LONGITUDE]
            )
            if error:
                errors["base"] = error
            else:
                self._site[CONF_WEATHER] = weather
                return await self._async_after_weather()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER, default=current.get(CONF_PROVIDER, PROVIDER_OPEN_METEO)
                ): _select(PROVIDERS_INTL, "provider"),
            }
        )
        return self.async_show_form(step_id="weather_intl", data_schema=schema, errors=errors)

    async def async_step_weather_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2c: weather from Home Assistant sensors (needs long-term statistics)."""
        errors: dict[str, str] = {}
        current = self._site.get(CONF_WEATHER, {}).get(CONF_HA_ENTITIES, {})
        if user_input is not None:
            for key in (CONF_TEMPERATURE_ENTITY, CONF_WIND_ENTITY, CONF_RADIATION_ENTITY):
                if user_input.get(key) and (
                    error := _validate_measurement_entity(self.hass, user_input[key])
                ):
                    errors[key] = error
            if not errors:
                self._site[CONF_WEATHER] = {
                    **self._site.get(CONF_WEATHER, {}),
                    CONF_PROVIDER: PROVIDER_HA_SENSORS,
                    CONF_HA_ENTITIES: {
                        key: user_input[key]
                        for key in (
                            CONF_TEMPERATURE_ENTITY,
                            CONF_WIND_ENTITY,
                            CONF_RADIATION_ENTITY,
                        )
                        if user_input.get(key)
                    },
                }
                return await self._async_after_weather()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TEMPERATURE_ENTITY,
                    description=_suggested(current.get(CONF_TEMPERATURE_ENTITY)),
                ): _entity(["temperature"]),
                vol.Optional(
                    CONF_WIND_ENTITY, description=_suggested(current.get(CONF_WIND_ENTITY))
                ): _entity(["wind_speed"]),
                vol.Optional(
                    CONF_RADIATION_ENTITY,
                    description=_suggested(current.get(CONF_RADIATION_ENTITY)),
                ): _entity(["irradiance"]),
            }
        )
        return self.async_show_form(step_id="weather_sensors", data_schema=schema, errors=errors)

    # --- step 3: situation -------------------------------------------------------------

    async def async_step_situation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: heating situation; prefills the generator drafts."""
        if user_input is not None:
            situation = user_input[CONF_SITUATION]
            self._site[CONF_SITUATION] = situation
            self._drafts = list(SITUATION_DRAFTS[situation])
            return await self.async_step_generator()
        gas, heat_pump = _detect_candidates(self.hass)
        schema = vol.Schema(
            {vol.Required(CONF_SITUATION, default="gas"): _select(SITUATIONS, "situation")}
        )
        return self.async_show_form(
            step_id="situation",
            data_schema=schema,
            description_placeholders={
                "gas_candidates": ", ".join(gas) or "-",
                "heat_pump_candidates": ", ".join(heat_pump) or "-",
            },
        )

    # --- step 4: generators (repeating) -----------------------------------------------

    async def async_step_generator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4.1: name, kind and role of the next generator."""
        if user_input is not None:
            self._current = dict(user_input)
            return await self.async_step_generator_details()
        if self._drafts:
            kind, role = self._drafts[0]
        else:
            kind, role = KIND_GAS_BOILER, ROLE_BOTH
        taken = {generator[CONF_NAME] for generator in self._generators}
        name = KIND_DEFAULTS[kind].name
        if name in taken:
            name = f"{name} {len(self._generators) + 1}"
        defaults = {CONF_NAME: name, CONF_KIND: kind, CONF_ROLE: role}
        return self.async_show_form(
            step_id="generator",
            data_schema=generator_base_schema(defaults),
            description_placeholders={"number": str(len(self._generators) + 1)},
        )

    async def async_step_generator_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4.2-4.5: sensors, conversion, DHW and pricing of the generator."""
        errors: dict[str, str] = {}
        kind = self._current[CONF_KIND]
        role = self._current[CONF_ROLE]
        defaults: Mapping[str, Any] = self._current
        if user_input is not None:
            flat = flatten_sections(user_input)
            defaults = {**self._current, **flat}
            errors = validate_generator_details(self.hass, kind, role, flat)
            if not errors:
                existing = {generator[CONF_GENERATOR_ID] for generator in self._generators}
                self._generators.append(
                    normalize_generator(self.hass, self._current, flat, existing)
                )
                if self._drafts:
                    self._drafts.pop(0)
                if self._drafts:
                    return await self.async_step_generator()
                return await self.async_step_generator_more()
        return self.async_show_form(
            step_id="generator_details",
            data_schema=generator_details_schema(kind, role, defaults),
            errors=errors,
            description_placeholders={"name": self._current[CONF_NAME]},
        )

    async def async_step_generator_more(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether another generator should be added."""
        return self.async_show_menu(
            step_id="generator_more",
            menu_options=["generator", "dhw"],
            description_placeholders={
                "generators": ", ".join(generator[CONF_NAME] for generator in self._generators)
                or "-"
            },
        )

    # --- step 5: DHW ---------------------------------------------------------------------

    def _dhw_summary(self) -> str:
        """Return a short per-generator DHW summary for the description."""
        parts = []
        for generator in self._generators:
            mode = generator.get(
                CONF_DHW_MODE, "-" if generator[CONF_ROLE] != ROLE_BOTH else DHW_BASELINE
            )
            parts.append(f"{generator[CONF_NAME]}: {generator[CONF_ROLE]} / {mode}")
        return "; ".join(parts) or "-"

    async def async_step_dhw(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 5: site-level hot water and cooking defaults."""
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (CONF_SUMMER_START, CONF_SUMMER_END):
                if not _validate_month_day(user_input[key]):
                    errors[key] = "invalid_month_day"
            if not errors:
                self._options[OPT_DHW] = {
                    CONF_DHW_OVERRIDE: user_input[CONF_DHW_OVERRIDE],
                    CONF_SUMMER_START: user_input[CONF_SUMMER_START].strip(),
                    CONF_SUMMER_END: user_input[CONF_SUMMER_END].strip(),
                }
                return await self.async_step_methods()
        return self.async_show_form(
            step_id="dhw",
            data_schema=dhw_schema(user_input or self._options.get(OPT_DHW, {})),
            errors=errors,
            description_placeholders={"summary": self._dhw_summary()},
        )

    # --- step 6: methods and season ----------------------------------------------------

    async def async_step_methods(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 6: degree-day methods and season start."""
        errors: dict[str, str] = {}
        defaults: Mapping[str, Any] = self._options.get(OPT_METHODS, {})
        if user_input is not None:
            flat = flatten_sections(user_input)
            defaults = flat
            if flat[CONF_METHODS_PRIMARY] not in flat[CONF_METHODS_ENABLED]:
                errors[CONF_METHODS_PRIMARY] = "primary_not_enabled"
            if not errors:
                self._options[OPT_METHODS] = flat
                return await self.async_step_history()
        return self.async_show_form(
            step_id="methods", data_schema=methods_schema(defaults), errors=errors
        )

    # --- step 7: history ---------------------------------------------------------------

    async def async_step_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 7: backfill and climatology years."""
        if user_input is not None:
            self._options[OPT_HISTORY] = {
                CONF_BACKFILL_YEARS: int(user_input[CONF_BACKFILL_YEARS]),
                CONF_CLIMATOLOGY_YEARS: int(user_input[CONF_CLIMATOLOGY_YEARS]),
                CONF_IMPORT_NOW: bool(user_input.get(CONF_IMPORT_NOW, False)),
            }
            return await self.async_step_summary()
        return self.async_show_form(
            step_id="history",
            data_schema=history_schema(self._options.get(OPT_HISTORY, {}), options=False),
        )

    # --- summary -----------------------------------------------------------------------

    async def async_step_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the summary and create the entry with generator subentries."""
        if user_input is not None:
            subentries = [
                ConfigSubentryData(
                    data=generator,
                    subentry_type=SUBENTRY_TYPE_GENERATOR,
                    title=generator[CONF_NAME],
                    unique_id=generator[CONF_GENERATOR_ID],
                )
                for generator in self._generators
            ]
            return self.async_create_entry(
                title=self._site[CONF_NAME],
                data=self._site,
                options=self._options,
                subentries=subentries,
            )
        weather = self._site.get(CONF_WEATHER, {})
        weather_text = weather.get(CONF_PROVIDER, "-")
        if weather.get(CONF_PROVIDER) == PROVIDER_KNMI and weather.get(CONF_STATION_ID):
            station = KNMI_STATIONS.get(weather[CONF_STATION_ID], (weather[CONF_STATION_ID], 0, 0))[
                0
            ]
            weather_text = f"{weather_text} {station}"
        methods = self._options.get(OPT_METHODS, {})
        history = self._options.get(OPT_HISTORY, {})
        generators = "; ".join(
            f"{generator[CONF_NAME]} ({generator[CONF_KIND]}, {generator[CONF_ROLE]}, "
            f"{generator.get(CONF_CONVERSION_MODE, '-')}, DHW {generator.get(CONF_DHW_MODE, '-')})"
            for generator in self._generators
        )
        return self.async_show_form(
            step_id="summary",
            data_schema=vol.Schema({}),
            description_placeholders={
                "site": f"{self._site[CONF_NAME]} ({self._site[CONF_LATITUDE]:.3f}, {self._site[CONF_LONGITUDE]:.3f}, {self._site[CONF_TIMEZONE]})",
                "weather": weather_text,
                "generators": generators or "-",
                "methods": ", ".join(methods.get(CONF_METHODS_ENABLED, []))
                + f" (primary {methods.get(CONF_METHODS_PRIMARY, '-')})",
                "season": str(methods.get(CONF_SEASON_START, SEASON_START_OCTOBER)),
                "backfill": str(history.get(CONF_BACKFILL_YEARS, DEFAULT_BACKFILL_YEARS)),
            },
            last_step=True,
        )

    # --- reconfigure -------------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure location, time zone and country, then the weather source."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        defaults = site_defaults_from_hass(self.hass)
        if user_input is not None:
            if dt_util.get_time_zone(user_input[CONF_TIMEZONE]) is None:
                errors[CONF_TIMEZONE] = "invalid_timezone"
            if not errors:
                location = user_input[CONF_LOCATION]
                self._site = {
                    **entry.data,
                    CONF_LATITUDE: float(location[CONF_LATITUDE]),
                    CONF_LONGITUDE: float(location[CONF_LONGITUDE]),
                    CONF_TIMEZONE: user_input[CONF_TIMEZONE],
                    CONF_COUNTRY: user_input[CONF_COUNTRY],
                }
                return await self._async_step_weather()
        self._site = dict(entry.data)
        timezones = await _async_timezones(self.hass)
        current_tz = entry.data.get(CONF_TIMEZONE, defaults.timezone)
        if current_tz not in timezones:
            timezones = sorted([*timezones, current_tz])
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCATION,
                    default={
                        CONF_LATITUDE: entry.data.get(CONF_LATITUDE, defaults.latitude),
                        CONF_LONGITUDE: entry.data.get(CONF_LONGITUDE, defaults.longitude),
                    },
                ): LocationSelector(LocationSelectorConfig(radius=False)),
                vol.Required(CONF_TIMEZONE, default=current_tz): SelectSelector(
                    SelectSelectorConfig(
                        options=timezones, mode=SelectSelectorMode.DROPDOWN, sort=False
                    )
                ),
                vol.Required(
                    CONF_COUNTRY,
                    default=entry.data.get(CONF_COUNTRY, defaults.country or "NL"),
                ): CountrySelector(),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def _async_finish_reconfigure(self) -> ConfigFlowResult:
        """Store the reconfigured site; ask for confirmation when the weather source changed."""
        entry = self._get_reconfigure_entry()
        changed = weather_signature_from_data(entry.data) != weather_signature_from_data(self._site)
        if changed and not self._reconfigure_confirmed:
            return await self.async_step_reconfigure_confirm()
        # The update listener registered in async_setup_entry reloads the entry.
        self.hass.config_entries.async_update_entry(entry, data=self._site)
        return self.async_abort(reason="reconfigure_successful")

    async def async_step_reconfigure_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm that the weather history is refetched and all records recomputed."""
        if user_input is not None:
            self._reconfigure_confirmed = True
            return await self._async_finish_reconfigure()
        return self.async_show_form(step_id="reconfigure_confirm", data_schema=vol.Schema({}))


# --------------------------------------------------------------------------------
# Options flow
# --------------------------------------------------------------------------------


class HeatprintOptionsFlow(OptionsFlow):
    """Options: methods, DHW, history, import, pricing, integrations, advanced."""

    def __init__(self) -> None:
        """Initialise import-wizard state."""
        super().__init__()
        self._import_text = ""
        self._import_generator = ""
        self._import_unit = UNIT_M3
        self._import_inspection: Any = None
        self._import_result: dict[str, Any] = {}
        self._sync_summary = "0 created, 0 updated"

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                OPT_METHODS,
                OPT_DHW,
                OPT_HISTORY,
                OPT_IMPORT,
                OPT_PRICING,
                OPT_INTEGRATIONS,
                OPT_ROOMS,
                OPT_SYNC_ROOMS,
                OPT_ADVANCED,
            ],
        )

    def _section(self, key: str) -> dict[str, Any]:
        """Return the stored values of an options section."""
        return dict(self.config_entry.options.get(key, {}))

    def _save(self, key: str, values: Mapping[str, Any]) -> ConfigFlowResult:
        """Store one options section and finish."""
        return self.async_create_entry(data={**self.config_entry.options, key: dict(values)})

    def _generator_choices(self) -> list[SelectOptionDict]:
        """Return generator subentries as select options."""
        return [
            SelectOptionDict(value=subentry.data[CONF_GENERATOR_ID], label=subentry.title)
            for subentry in self.config_entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_GENERATOR
            and subentry.data.get(CONF_GENERATOR_ID)
        ]

    def _generator_unit(self, generator_id: str) -> str:
        """Return the stored carrier unit of a generator, defaulting to m³."""
        for subentry in self.config_entry.subentries.values():
            if (
                subentry.subentry_type == SUBENTRY_TYPE_GENERATOR
                and subentry.data.get(CONF_GENERATOR_ID) == generator_id
            ):
                return str(subentry.data.get(CONF_UNIT, UNIT_M3))
        return UNIT_M3

    async def _async_read_csv_source(self, user_input: Mapping[str, Any]) -> tuple[str, str | None]:
        """Return CSV text from paste, uploaded file or a path under /config."""
        pasted = str(user_input.get(ATTR_CSV) or "").strip()
        if pasted:
            return pasted, None
        file_id = user_input.get("file")
        if file_id:
            try:
                from homeassistant.components.file_upload import process_uploaded_file
            except ImportError:
                return "", "csv_unreadable"
            try:
                with process_uploaded_file(self.hass, file_id) as path:
                    return path.read_text(encoding="utf-8-sig"), None
            except OSError:
                return "", "csv_unreadable"
        path_value = str(user_input.get(ATTR_PATH) or "").strip()
        if not path_value:
            return "", "no_source"
        base = Path(self.hass.config.config_dir).resolve()
        candidate = Path(path_value)
        resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
        if resolved != base and base not in resolved.parents:
            return "", "path_not_allowed"
        try:
            return await self.hass.async_add_executor_job(resolved.read_text, "utf-8-sig"), None
        except OSError:
            return "", "csv_unreadable"

    def _preview_text(self) -> str:
        """Format the first parsed rows for the confirm step."""
        inspection = self._import_inspection
        if inspection is None or not inspection.preview:
            return "—"
        lines = [f"{stamp} → {value}" for stamp, value in inspection.preview]
        extra = len(inspection.readings) - len(inspection.preview)
        if extra > 0:
            lines.append(f"… +{extra} more")
        return "; ".join(lines)

    async def async_step_import_readings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Paste or load a CSV, pick generator and unit; auto-detect columns."""
        errors: dict[str, str] = {}
        generators = self._generator_choices()
        if not generators:
            return self.async_abort(reason="no_generators")
        if user_input is not None:
            text, error = await self._async_read_csv_source(user_input)
            if error:
                errors["base"] = error
            else:
                inspection = inspect_readings_csv(text)
                if inspection.error == "empty":
                    errors["base"] = "csv_empty"
                elif inspection.error == "no_rows":
                    errors["base"] = "csv_invalid"
                else:
                    self._import_text = text
                    self._import_inspection = inspection
                    self._import_generator = user_input[CONF_GENERATOR_ID]
                    self._import_unit = user_input[CONF_UNIT]
                    if inspection.ambiguous:
                        return await self.async_step_import_columns()
                    return await self.async_step_import_preview()
        default_generator = generators[0]["value"]
        schema_fields: dict[Any, Any] = {
            vol.Optional(ATTR_CSV): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Optional(ATTR_PATH): TextSelector(),
            vol.Optional("file"): FileSelector(
                FileSelectorConfig(accept=".csv,text/csv,text/plain")
            ),
            vol.Required(CONF_GENERATOR_ID, default=default_generator): SelectSelector(
                SelectSelectorConfig(options=generators, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_UNIT, default=self._generator_unit(default_generator)): _select(
                IMPORT_UNITS, "import_unit"
            ),
        }
        return self.async_show_form(
            step_id="import_readings",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    async def async_step_import_columns(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which header is the date and which is the reading (ambiguous CSV)."""
        errors: dict[str, str] = {}
        inspection = self._import_inspection
        headers = list(inspection.headers) if inspection is not None else []
        options = [SelectOptionDict(value=header, label=header) for header in headers]
        if user_input is not None:
            inspection = inspect_readings_csv(
                self._import_text,
                date_col=user_input[ATTR_DATE_COLUMN],
                value_col=user_input[ATTR_READING_COLUMN],
            )
            if inspection.error or not inspection.readings:
                errors["base"] = "csv_invalid"
            else:
                self._import_inspection = inspection
                return await self.async_step_import_preview()
        suggested_date = inspection.date_column if inspection else (headers[0] if headers else "")
        suggested_reading = (
            inspection.reading_column if inspection else (headers[1] if len(headers) > 1 else "")
        )
        schema = vol.Schema(
            {
                vol.Required(ATTR_DATE_COLUMN, default=suggested_date): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(ATTR_READING_COLUMN, default=suggested_reading): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(
            step_id="import_columns",
            data_schema=schema,
            errors=errors,
            description_placeholders={"headers": ", ".join(headers) or "—"},
        )

    async def async_step_import_preview(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a preview and import + recompute on confirm."""
        inspection = self._import_inspection
        if user_input is not None and inspection is not None:
            readings = list(inspection.readings)
            if self._import_unit == UNIT_GJ:
                readings = [(stamp, value * GJ_TO_KWH) for stamp, value in readings]
            coordinator = self.config_entry.runtime_data
            self._import_result = await coordinator.async_import_readings(
                self._import_generator, readings
            )
            return await self.async_step_import_done()
        return self.async_show_form(
            step_id="import_preview",
            data_schema=vol.Schema({}),
            description_placeholders={
                "count": str(len(inspection.readings) if inspection else 0),
                "preview": self._preview_text(),
                "date_column": (inspection.date_column if inspection else "—") or "—",
                "reading_column": (inspection.reading_column if inspection else "—") or "—",
                "delimiter": inspection.delimiter if inspection else ";",
                "decimal": inspection.decimal if inspection else ",",
                "generator": self._import_generator,
                "unit": self._import_unit,
            },
            last_step=False,
        )

    async def async_step_import_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the import result; options are unchanged."""
        if user_input is not None:
            return self.async_create_entry(data=self.config_entry.options)
        result = self._import_result
        return self.async_show_form(
            step_id="import_done",
            data_schema=vol.Schema({}),
            description_placeholders={
                "imported_days": str(result.get("imported_days", 0)),
                "first_day": str(result.get("first_day", "—")),
                "last_day": str(result.get("last_day", "—")),
                "gaps": str(len(result.get("gaps") or [])),
            },
            last_step=True,
        )

    async def async_step_methods(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Methods and season."""
        errors: dict[str, str] = {}
        defaults: Mapping[str, Any] = self._section(OPT_METHODS)
        if user_input is not None:
            flat = flatten_sections(user_input)
            defaults = flat
            if flat[CONF_METHODS_PRIMARY] not in flat[CONF_METHODS_ENABLED]:
                errors[CONF_METHODS_PRIMARY] = "primary_not_enabled"
            if not errors:
                return self._save(OPT_METHODS, flat)
        return self.async_show_form(
            step_id="methods", data_schema=methods_schema(defaults), errors=errors
        )

    async def async_step_dhw(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hot water and cooking defaults."""
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (CONF_SUMMER_START, CONF_SUMMER_END):
                if not _validate_month_day(user_input[key]):
                    errors[key] = "invalid_month_day"
            if not errors:
                return self._save(
                    OPT_DHW,
                    {
                        CONF_DHW_OVERRIDE: user_input[CONF_DHW_OVERRIDE],
                        CONF_SUMMER_START: user_input[CONF_SUMMER_START].strip(),
                        CONF_SUMMER_END: user_input[CONF_SUMMER_END].strip(),
                    },
                )
        return self.async_show_form(
            step_id="dhw",
            data_schema=dhw_schema(user_input or self._section(OPT_DHW)),
            errors=errors,
            description_placeholders={"summary": self._generator_dhw_summary()},
        )

    def _generator_dhw_summary(self) -> str:
        """Summarise the DHW mode per generator subentry."""
        parts = []
        for subentry in self.config_entry.subentries.values():
            if subentry.subentry_type != SUBENTRY_TYPE_GENERATOR:
                continue
            parts.append(
                f"{subentry.title}: {subentry.data.get(CONF_ROLE, '-')} / {subentry.data.get(CONF_DHW_MODE, '-')}"
            )
        return "; ".join(parts) or "-"

    async def async_step_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Backfill and climatology years; optional recompute from a date."""
        if user_input is not None:
            values = {
                **self._section(OPT_HISTORY),
                CONF_BACKFILL_YEARS: int(user_input[CONF_BACKFILL_YEARS]),
                CONF_CLIMATOLOGY_YEARS: int(user_input[CONF_CLIMATOLOGY_YEARS]),
            }
            if user_input.get(CONF_RECOMPUTE_FROM):
                values[CONF_RECOMPUTE_FROM] = str(user_input[CONF_RECOMPUTE_FROM])
                values["recompute_token"] = dt_util.utcnow().isoformat()
            return self._save(OPT_HISTORY, values)
        return self.async_show_form(
            step_id="history", data_schema=history_schema(self._section(OPT_HISTORY), options=True)
        )

    async def async_step_pricing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Default CO2 factors and an optional live CO2 sensor."""
        current = self._section(OPT_PRICING)
        if user_input is not None:
            values = {
                CONF_GAS_CO2_FACTOR: float(user_input[CONF_GAS_CO2_FACTOR]),
                CONF_ELECTRIC_CO2_FACTOR: float(user_input[CONF_ELECTRIC_CO2_FACTOR]),
                CONF_DISTRICT_CO2_FACTOR: float(user_input[CONF_DISTRICT_CO2_FACTOR]),
            }
            if user_input.get(CONF_CO2_ENTITY):
                values[CONF_CO2_ENTITY] = user_input[CONF_CO2_ENTITY]
            return self._save(OPT_PRICING, values)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_GAS_CO2_FACTOR,
                    default=current.get(CONF_GAS_CO2_FACTOR, DEFAULT_GAS_CO2_KG_PER_M3),
                ): _number(0.0, 10.0, 0.001, "kg/m³"),
                vol.Required(
                    CONF_ELECTRIC_CO2_FACTOR,
                    default=current.get(CONF_ELECTRIC_CO2_FACTOR, DEFAULT_ELECTRIC_CO2_KG_PER_KWH),
                ): _number(0.0, 10.0, 0.001, "kg/kWh"),
                vol.Required(
                    CONF_DISTRICT_CO2_FACTOR,
                    default=current.get(CONF_DISTRICT_CO2_FACTOR, DEFAULT_DISTRICT_CO2_KG_PER_KWH),
                ): _number(0.0, 10.0, 0.001, "kg/kWh"),
                vol.Optional(
                    CONF_CO2_ENTITY, description=_suggested(current.get(CONF_CO2_ENTITY))
                ): _entity(),
            }
        )
        return self.async_show_form(step_id="pricing", data_schema=schema)

    async def async_step_integrations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """mindergas.nl bridge: token, generator and daily push."""
        current = self._section(OPT_INTEGRATIONS)
        generators = [
            SelectOptionDict(value=subentry.data[CONF_GENERATOR_ID], label=subentry.title)
            for subentry in self.config_entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_GENERATOR
        ]
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_MINDERGAS_TOKEN, "")).strip() or current.get(
                CONF_MINDERGAS_TOKEN, ""
            )
            values: dict[str, Any] = {
                CONF_MINDERGAS_TOKEN: token,
                CONF_MINDERGAS_DAILY_PUSH: bool(user_input.get(CONF_MINDERGAS_DAILY_PUSH, False)),
            }
            if user_input.get(CONF_MINDERGAS_GENERATOR):
                values[CONF_MINDERGAS_GENERATOR] = user_input[CONF_MINDERGAS_GENERATOR]
            if values[CONF_MINDERGAS_DAILY_PUSH] and not token:
                errors[CONF_MINDERGAS_TOKEN] = "token_required"
            if values[CONF_MINDERGAS_DAILY_PUSH] and not values.get(CONF_MINDERGAS_GENERATOR):
                errors[CONF_MINDERGAS_GENERATOR] = "generator_required"
            if not errors:
                return self._save(OPT_INTEGRATIONS, values)
        fields: dict[Any, Any] = {
            # The stored token is never shown again; leave empty to keep it.
            vol.Optional(CONF_MINDERGAS_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
        if generators:
            fields[
                vol.Optional(
                    CONF_MINDERGAS_GENERATOR,
                    description=_suggested(current.get(CONF_MINDERGAS_GENERATOR)),
                )
            ] = SelectSelector(
                SelectSelectorConfig(options=generators, mode=SelectSelectorMode.DROPDOWN)
            )
        fields[
            vol.Required(
                CONF_MINDERGAS_DAILY_PUSH, default=current.get(CONF_MINDERGAS_DAILY_PUSH, False)
            )
        ] = BooleanSelector()
        return self.async_show_form(
            step_id="integrations",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "token_state": "set" if current.get(CONF_MINDERGAS_TOKEN) else "not set"
            },
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """PBL parameters, wind coefficient, outlier threshold and minimum fit days."""
        current = self._section(OPT_ADVANCED)
        if user_input is not None:
            return self._save(OPT_ADVANCED, flatten_sections(user_input))
        pbl = {
            vol.Required(
                CONF_PBL_TST_WINTER,
                default=current.get(CONF_PBL_TST_WINTER, DEFAULT_PBL_TST["winter"]),
            ): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(
                CONF_PBL_TST_SHOULDER,
                default=current.get(CONF_PBL_TST_SHOULDER, DEFAULT_PBL_TST["shoulder"]),
            ): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(
                CONF_PBL_TST_TRANSITION,
                default=current.get(CONF_PBL_TST_TRANSITION, DEFAULT_PBL_TST["transition"]),
            ): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(
                CONF_PBL_TST_SUMMER,
                default=current.get(CONF_PBL_TST_SUMMER, DEFAULT_PBL_TST["summer"]),
            ): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(
                CONF_PBL_RER_WINTER,
                default=current.get(CONF_PBL_RER_WINTER, DEFAULT_PBL_RER["winter"]),
            ): _number(0.1, 2.0, 0.01),
            vol.Required(
                CONF_PBL_RER_SHOULDER,
                default=current.get(CONF_PBL_RER_SHOULDER, DEFAULT_PBL_RER["shoulder"]),
            ): _number(0.1, 2.0, 0.01),
            vol.Required(
                CONF_PBL_RER_TRANSITION,
                default=current.get(CONF_PBL_RER_TRANSITION, DEFAULT_PBL_RER["transition"]),
            ): _number(0.1, 2.0, 0.01),
            vol.Required(
                CONF_PBL_RER_SUMMER,
                default=current.get(CONF_PBL_RER_SUMMER, DEFAULT_PBL_RER["summer"]),
            ): _number(0.1, 2.0, 0.01),
            vol.Required(CONF_PBL_TOP, default=current.get(CONF_PBL_TOP, DEFAULT_PBL_TOP)): _number(
                0.0, 5.0, 0.01
            ),
            vol.Required(
                CONF_PBL_WIND_SQRT_COEF,
                default=current.get(CONF_PBL_WIND_SQRT_COEF, round(DEFAULT_PBL_WIND_SQRT_COEF, 3)),
            ): _number(0.0, 10.0, 0.001),
        }
        fit = {
            vol.Required(
                CONF_OUTLIER_THRESHOLD,
                default=current.get(CONF_OUTLIER_THRESHOLD, DEFAULT_OUTLIER_THRESHOLD),
            ): _number(2.0, 10.0, 0.1),
            vol.Required(
                CONF_MIN_FIT_DAYS, default=current.get(CONF_MIN_FIT_DAYS, DEFAULT_MIN_FIT_DAYS)
            ): _number(15, 120, 1),
        }
        schema = vol.Schema(
            {
                vol.Required(SECTION_PBL): section(vol.Schema(pbl), {"collapsed": True}),
                vol.Required(SECTION_FIT): section(vol.Schema(fit), {"collapsed": False}),
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)

    async def async_step_rooms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Default emitter output, auto-sync from HA areas and allocation on/off."""
        current = self._section(OPT_ROOMS)
        if user_input is not None:
            exclude = user_input.get(CONF_ROOMS_EXCLUDE_AREAS) or []
            if isinstance(exclude, str):
                exclude = [exclude]
            values = {
                CONF_ROOMS_ALLOCATION: bool(user_input[CONF_ROOMS_ALLOCATION]),
                CONF_ROOMS_AUTO_SYNC: bool(user_input[CONF_ROOMS_AUTO_SYNC]),
                CONF_ROOMS_EXCLUDE_AREAS: list(exclude),
                CONF_ROOMS_MIN_FIT_DAYS: int(user_input[CONF_ROOMS_MIN_FIT_DAYS]),
                CONF_OUTPUT_W_PER_M2_RADIATOR: float(user_input[CONF_OUTPUT_W_PER_M2_RADIATOR]),
                CONF_OUTPUT_W_PER_M2_UNDERFLOOR: float(
                    user_input[CONF_OUTPUT_W_PER_M2_UNDERFLOOR]
                ),
                CONF_OUTPUT_W_PER_M2_ELECTRIC: float(user_input[CONF_OUTPUT_W_PER_M2_ELECTRIC]),
                CONF_OUTPUT_W_PER_M2_OTHER: float(user_input[CONF_OUTPUT_W_PER_M2_OTHER]),
            }
            if user_input.get(CONF_ROOMS_SYNC_NOW):
                sync_rooms_from_hass(self.hass, self.config_entry)
            return self._save(OPT_ROOMS, values)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROOMS_ALLOCATION,
                    default=current.get(CONF_ROOMS_ALLOCATION, DEFAULT_ROOMS_ALLOCATION),
                ): BooleanSelector(),
                vol.Required(
                    CONF_ROOMS_AUTO_SYNC,
                    default=current.get(CONF_ROOMS_AUTO_SYNC, DEFAULT_ROOMS_AUTO_SYNC),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_ROOMS_EXCLUDE_AREAS,
                    description=_suggested(current.get(CONF_ROOMS_EXCLUDE_AREAS) or []),
                ): AreaSelector(AreaSelectorConfig(multiple=True)),
                vol.Required(
                    CONF_ROOMS_SYNC_NOW, default=False
                ): BooleanSelector(),
                vol.Required(
                    CONF_ROOMS_MIN_FIT_DAYS,
                    default=current.get(CONF_ROOMS_MIN_FIT_DAYS, DEFAULT_ROOMS_MIN_FIT_DAYS),
                ): _number(15, 120, 1),
                vol.Required(
                    CONF_OUTPUT_W_PER_M2_RADIATOR,
                    default=current.get(
                        CONF_OUTPUT_W_PER_M2_RADIATOR, DEFAULT_OUTPUT_W_PER_M2["radiator"]
                    ),
                ): _number(10, 200, 1, "W/m²"),
                vol.Required(
                    CONF_OUTPUT_W_PER_M2_UNDERFLOOR,
                    default=current.get(
                        CONF_OUTPUT_W_PER_M2_UNDERFLOOR, DEFAULT_OUTPUT_W_PER_M2["underfloor"]
                    ),
                ): _number(10, 200, 1, "W/m²"),
                vol.Required(
                    CONF_OUTPUT_W_PER_M2_ELECTRIC,
                    default=current.get(
                        CONF_OUTPUT_W_PER_M2_ELECTRIC, DEFAULT_OUTPUT_W_PER_M2["electric"]
                    ),
                ): _number(10, 200, 1, "W/m²"),
                vol.Required(
                    CONF_OUTPUT_W_PER_M2_OTHER,
                    default=current.get(
                        CONF_OUTPUT_W_PER_M2_OTHER, DEFAULT_OUTPUT_W_PER_M2["other"]
                    ),
                ): _number(10, 200, 1, "W/m²"),
            }
        )
        return self.async_show_form(step_id="rooms", data_schema=schema)

    async def async_step_sync_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """One-click sync of room subentries from Home Assistant areas."""
        from .dashboard import async_ensure_rooms_dashboard

        discovery = discover_rooms_from_hass(
            self.hass,
            exclude_area_ids=self._section(OPT_ROOMS).get(CONF_ROOMS_EXCLUDE_AREAS) or [],
        )
        if user_input is not None:
            plan = sync_rooms_from_hass(self.hass, self.config_entry)
            self._sync_summary = plan.summary()
            try:
                await async_ensure_rooms_dashboard(self.hass, self.config_entry, recreate=True)
            except Exception:  # noqa: BLE001 - dashboard must not fail options
                _LOGGER.exception("Could not refresh the Heatprint rooms dashboard after sync")
            return await self.async_step_sync_rooms_done()
        return self.async_show_form(
            step_id="sync_rooms",
            data_schema=vol.Schema({}),
            description_placeholders={
                "rooms": discovery.room_summary(),
                "skipped": discovery.skipped_summary(),
            },
        )

    async def async_step_sync_rooms_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the sync result; options stay as they are."""
        if user_input is not None:
            return self.async_create_entry(data=self.config_entry.options)
        return self.async_show_form(
            step_id="sync_rooms_done",
            data_schema=vol.Schema({}),
            description_placeholders={"summary": self._sync_summary},
            last_step=True,
        )


# --------------------------------------------------------------------------------
# Subentry flows
# --------------------------------------------------------------------------------


class _SubentryFlowBase(ConfigSubentryFlow):
    """Shared helpers for the subentry flows (compatible with HA 2026.9 and newer)."""

    @property
    def _config_entry(self) -> ConfigEntry:
        """Return the config entry this subentry flow belongs to."""
        return self.hass.config_entries.async_get_known_entry(self.handler[0])

    def _existing_ids(self, subentry_type: str, id_key: str) -> set[str]:
        """Return the ids of existing subentries of a type."""
        return {
            str(subentry.data.get(id_key))
            for subentry in self._config_entry.subentries.values()
            if subentry.subentry_type == subentry_type and subentry.data.get(id_key)
        }


class GeneratorSubentryFlowHandler(_SubentryFlowBase):
    """Add or reconfigure a heat generator (CONFIG_FLOW 4.1-4.5)."""

    def __init__(self) -> None:
        """Initialise flow state."""
        self._base: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Name, kind and role of a new generator."""
        if user_input is not None:
            self._base = dict(user_input)
            return await self.async_step_details()
        return self.async_show_form(step_id="user", data_schema=generator_base_schema({}))

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Sensors, conversion, DHW and pricing of a new generator."""
        errors: dict[str, str] = {}
        kind, role = self._base[CONF_KIND], self._base[CONF_ROLE]
        defaults: Mapping[str, Any] = self._base
        if user_input is not None:
            flat = flatten_sections(user_input)
            defaults = {**self._base, **flat}
            errors = validate_generator_details(self.hass, kind, role, flat)
            if not errors:
                existing = self._existing_ids(SUBENTRY_TYPE_GENERATOR, CONF_GENERATOR_ID)
                generator = normalize_generator(self.hass, self._base, flat, existing)
                return self.async_create_entry(
                    title=generator[CONF_NAME],
                    data=generator,
                    unique_id=generator[CONF_GENERATOR_ID],
                )
        return self.async_show_form(
            step_id="details",
            data_schema=generator_details_schema(kind, role, defaults),
            errors=errors,
            description_placeholders={"name": self._base[CONF_NAME]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change name, kind and role of an existing generator."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            self._base = {**subentry.data, **user_input}
            return await self.async_step_reconfigure_details()
        return self.async_show_form(
            step_id="reconfigure", data_schema=generator_base_schema(subentry.data)
        )

    async def async_step_reconfigure_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change sensors, conversion, DHW and pricing of an existing generator."""
        errors: dict[str, str] = {}
        subentry = self._get_reconfigure_subentry()
        kind, role = self._base[CONF_KIND], self._base[CONF_ROLE]
        defaults: Mapping[str, Any] = self._base
        if user_input is not None:
            flat = flatten_sections(user_input)
            defaults = {**self._base, **flat}
            errors = validate_generator_details(self.hass, kind, role, flat)
            if not errors:
                generator = normalize_generator(
                    self.hass,
                    self._base,
                    flat,
                    set(),
                    keep_id=str(subentry.data[CONF_GENERATOR_ID]),
                )
                # The config entry update listener reloads the entry; a changed energy entity
                # is recomputed from the first day the new sensor has statistics.
                return self.async_update_and_abort(
                    self._config_entry, subentry, data=generator, title=generator[CONF_NAME]
                )
        return self.async_show_form(
            step_id="reconfigure_details",
            data_schema=generator_details_schema(kind, role, defaults),
            errors=errors,
            description_placeholders={"name": self._base[CONF_NAME]},
        )


def measure_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for a measure subentry."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): TextSelector(),
            vol.Required(
                CONF_DATE, default=defaults.get(CONF_DATE, dt_util.now().date().isoformat())
            ): DateSelector(),
            vol.Required(CONF_CATEGORY, default=defaults.get(CONF_CATEGORY, "insulation")): _select(
                MEASURE_CATEGORIES, "measure_category"
            ),
            vol.Optional(
                CONF_NOTES, description=_suggested(defaults.get(CONF_NOTES))
            ): TextSelector(TextSelectorConfig(multiline=True)),
        }
    )


class MeasureSubentryFlowHandler(_SubentryFlowBase):
    """Add or reconfigure an energy-saving measure."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add a measure."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            if not errors:
                existing = self._existing_ids(SUBENTRY_TYPE_MEASURE, CONF_MEASURE_ID)
                measure_id = _unique_slug(name, existing, "measure")
                data = {
                    CONF_MEASURE_ID: measure_id,
                    CONF_NAME: name,
                    CONF_DATE: str(user_input[CONF_DATE]),
                    CONF_CATEGORY: user_input[CONF_CATEGORY],
                    CONF_NOTES: str(user_input.get(CONF_NOTES, "")),
                }
                return self.async_create_entry(title=name, data=data, unique_id=measure_id)
        return self.async_show_form(
            step_id="user", data_schema=measure_schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a measure."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            if not errors:
                data = {
                    **subentry.data,
                    CONF_NAME: name,
                    CONF_DATE: str(user_input[CONF_DATE]),
                    CONF_CATEGORY: user_input[CONF_CATEGORY],
                    CONF_NOTES: str(user_input.get(CONF_NOTES, "")),
                }
                return self.async_update_and_abort(
                    self._config_entry, subentry, data=data, title=name
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=measure_schema(user_input or subentry.data),
            errors=errors,
        )


def _detect_demand_kind(hass: HomeAssistant, entity_id: str | None) -> str:
    """Guess demand_kind from the entity's domain and unit (CONFIG_FLOW room)."""
    if not entity_id or (state := hass.states.get(entity_id)) is None:
        return DEMAND_KIND_PERCENTAGE
    domain = entity_id.split(".", 1)[0]
    if domain in ("binary_sensor", "climate", "switch"):
        return DEMAND_KIND_BINARY
    unit = str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or "")
    device_class = state.attributes.get("device_class")
    state_class = state.attributes.get("state_class")
    if device_class == "energy" or unit in ENERGY_UNITS or state_class in STATE_CLASS_CUMULATIVE:
        return DEMAND_KIND_METERED
    if unit in ("%", "percent"):
        return DEMAND_KIND_PERCENTAGE
    if "valve" in f"{state.name} {entity_id}".lower():
        return DEMAND_KIND_VALVE
    return DEMAND_KIND_PERCENTAGE


@callback
def validate_room(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, str]:
    """Validate a room subentry (CONFIG_FLOW room)."""
    errors: dict[str, str] = {}
    entity_id = data.get(CONF_DEMAND_ENTITY)
    if not entity_id:
        errors[CONF_DEMAND_ENTITY] = "entity_not_found"
        return errors
    state = hass.states.get(entity_id)
    if state is None:
        errors[CONF_DEMAND_ENTITY] = "entity_not_found"
        return errors
    kind = data.get(CONF_DEMAND_KIND, DEMAND_KIND_PERCENTAGE)
    domain = entity_id.split(".", 1)[0]
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if kind == DEMAND_KIND_METERED:
        if error := _validate_cumulative_entity(hass, entity_id, ENERGY_UNITS):
            errors[CONF_DEMAND_ENTITY] = (
                "demand_kind_mismatch" if error == "unit_mismatch" else error
            )
    elif kind == DEMAND_KIND_BINARY:
        if domain not in ("binary_sensor", "climate", "switch", "sensor"):
            errors[CONF_DEMAND_ENTITY] = "demand_kind_mismatch"
    elif kind in (DEMAND_KIND_PERCENTAGE, DEMAND_KIND_VALVE):
        if domain == "binary_sensor":
            errors[CONF_DEMAND_ENTITY] = "demand_kind_mismatch"
        elif unit and unit in ENERGY_UNITS:
            # Percent/valve may be unitless or %; an energy meter is the wrong kind.
            errors[CONF_DEMAND_ENTITY] = "demand_kind_mismatch"
    temperature = data.get(CONF_ROOM_TEMPERATURE_ENTITY)
    if temperature and hass.states.get(temperature) is None:
        errors[CONF_ROOM_TEMPERATURE_ENTITY] = "entity_not_found"
    return errors


def room_schema(defaults: Mapping[str, Any], *, show_price: bool) -> vol.Schema:
    """Schema for a room subentry."""
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_AREA_ID, description=_suggested(defaults.get(CONF_AREA_ID))
        ): AreaSelector(AreaSelectorConfig()),
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): TextSelector(),
        vol.Required(
            CONF_DEMAND_ENTITY, description=_suggested(defaults.get(CONF_DEMAND_ENTITY))
        ): EntitySelector(
            EntitySelectorConfig(domain=["sensor", "binary_sensor", "climate", "switch"])
        ),
        vol.Required(
            CONF_DEMAND_KIND, default=defaults.get(CONF_DEMAND_KIND, DEMAND_KIND_PERCENTAGE)
        ): _select(DEMAND_KINDS, "demand_kind"),
        vol.Optional(
            CONF_ROOM_TEMPERATURE_ENTITY,
            description=_suggested(defaults.get(CONF_ROOM_TEMPERATURE_ENTITY)),
        ): EntitySelector(EntitySelectorConfig(domain=["sensor", "climate"])),
        vol.Required(
            CONF_EMITTER_KIND, default=defaults.get(CONF_EMITTER_KIND, EMITTER_KIND_RADIATOR)
        ): _select(EMITTER_KINDS, "emitter_kind"),
        vol.Optional(
            CONF_RATED_OUTPUT_W, description=_suggested(defaults.get(CONF_RATED_OUTPUT_W))
        ): _number(50, 20000, 10, "W"),
        vol.Optional(
            CONF_FLOOR_AREA_M2, description=_suggested(defaults.get(CONF_FLOOR_AREA_M2))
        ): _number(1, 200, 0.1, "m²"),
        vol.Optional(CONF_VOLUME_M3, description=_suggested(defaults.get(CONF_VOLUME_M3))): _number(
            1, 800, 0.1, "m³"
        ),
        vol.Required(CONF_ENABLED, default=defaults.get(CONF_ENABLED, True)): BooleanSelector(),
    }
    if show_price:
        fields[
            vol.Optional(CONF_PRICE_ENTITY, description=_suggested(defaults.get(CONF_PRICE_ENTITY)))
        ] = _entity()
    return vol.Schema(fields)


def normalize_room(
    data: Mapping[str, Any], existing_ids: set[str], keep_id: str | None = None
) -> dict[str, Any]:
    """Build flat room subentry data."""
    name = str(data.get(CONF_NAME) or "").strip() or "Room"
    room_id = keep_id or _unique_slug(name, existing_ids, "room")
    result: dict[str, Any] = {
        CONF_ROOM_ID: room_id,
        CONF_NAME: name,
        CONF_DEMAND_ENTITY: data[CONF_DEMAND_ENTITY],
        CONF_DEMAND_KIND: data.get(CONF_DEMAND_KIND, DEMAND_KIND_PERCENTAGE),
        CONF_EMITTER_KIND: data.get(CONF_EMITTER_KIND, EMITTER_KIND_RADIATOR),
        CONF_ENABLED: bool(data.get(CONF_ENABLED, True)),
    }
    for key in (
        CONF_AREA_ID,
        CONF_ROOM_TEMPERATURE_ENTITY,
        CONF_PRICE_ENTITY,
    ):
        if data.get(key):
            result[key] = data[key]
    for key in (CONF_RATED_OUTPUT_W, CONF_FLOOR_AREA_M2, CONF_VOLUME_M3):
        if data.get(key) is not None:
            result[key] = float(data[key])
    return result


class RoomSubentryFlowHandler(_SubentryFlowBase):
    """Add or reconfigure a room (CONFIG_FLOW room)."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add a room."""
        errors: dict[str, str] = {}
        defaults: dict[str, Any] = dict(user_input or {})
        if user_input is None:
            defaults[CONF_DEMAND_KIND] = DEMAND_KIND_PERCENTAGE
        elif user_input.get(CONF_DEMAND_ENTITY) and CONF_DEMAND_KIND not in (user_input or {}):
            defaults[CONF_DEMAND_KIND] = _detect_demand_kind(
                self.hass, user_input.get(CONF_DEMAND_ENTITY)
            )
        if user_input is not None:
            name = str(user_input.get(CONF_NAME) or "").strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            errors.update(validate_room(self.hass, user_input))
            if not errors:
                existing = self._existing_ids(SUBENTRY_TYPE_ROOM, CONF_ROOM_ID)
                room = normalize_room(user_input, existing)
                return self.async_create_entry(
                    title=room[CONF_NAME], data=room, unique_id=room[CONF_ROOM_ID]
                )
        show_price = (user_input or {}).get(CONF_DEMAND_KIND) == DEMAND_KIND_METERED
        return self.async_show_form(
            step_id="user",
            data_schema=room_schema(defaults, show_price=show_price or True),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change a room."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        defaults: Mapping[str, Any] = user_input or subentry.data
        if user_input is not None:
            name = str(user_input.get(CONF_NAME) or "").strip()
            if not name:
                errors[CONF_NAME] = "invalid_name"
            errors.update(validate_room(self.hass, user_input))
            if not errors:
                room = normalize_room(user_input, set(), keep_id=str(subentry.data[CONF_ROOM_ID]))
                return self.async_update_and_abort(
                    self._config_entry, subentry, data=room, title=room[CONF_NAME]
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=room_schema(defaults, show_price=True),
            errors=errors,
        )
