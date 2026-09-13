"""Config flow for Heatprint (CONFIG_FLOW.md).

Main flow: site -> weather source -> heating situation -> generators (repeating)
-> DHW -> methods and season -> history -> summary. Generators become
``generator`` subentries; measures are added later as ``measure`` subentries.
The options flow manages methods, DHW, history, pricing, integrations and
advanced parameters; the reconfigure flow changes location and weather source.
"""

from __future__ import annotations

import math
import re
import zoneinfo
from collections.abc import Mapping
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
    BooleanSelector,
    CountrySelector,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
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
    CONF_DHW_ELECTRIC_ENTITY,
    CONF_DHW_ENTITY,
    CONF_DHW_FIXED_PER_DAY,
    CONF_DHW_MODE,
    CONF_DHW_OVERRIDE,
    CONF_DISTRICT_CO2_FACTOR,
    CONF_EFFICIENCY,
    CONF_ELECTRIC_CO2_FACTOR,
    CONF_ELECTRIC_ENTITY,
    CONF_ENERGY_ENTITY,
    CONF_FACTOR,
    CONF_FALLBACK,
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
    CONF_RECOMPUTE_FROM,
    CONF_ROLE,
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
    DEFAULT_PBL_RER,
    DEFAULT_PBL_TOP,
    DEFAULT_PBL_TST,
    DEFAULT_PBL_WIND_SQRT_COEF,
    DEFAULT_SCOP,
    DEFAULT_SITE_NAME,
    DEFAULT_SUMMER_END,
    DEFAULT_SUMMER_START,
    DHW_BASELINE,
    DHW_MEASURED,
    DHW_MODES,
    DHW_OVERRIDE_KEEP,
    DHW_OVERRIDE_OPTIONS,
    DOMAIN,
    ENERGY_UNITS,
    FALLBACKS,
    GAS_UNITS,
    GENERATOR_KINDS,
    HEAT_PUMP_CONVERSION_MODES,
    HEAT_UNITS,
    HEATING_VALUE_HS,
    HEATING_VALUE_OPTIONS,
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
    OPT_INTEGRATIONS,
    OPT_METHODS,
    OPT_PRICING,
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
    UNIT_GJ,
    UNIT_KWH,
    UNIT_M3,
)
from .core_api import (
    WeatherCannotConnect,
    WeatherNoData,
    async_test_weather,
    weather_signature_from_data,
)

STATE_CLASS_CUMULATIVE = {"total", "total_increasing"}
MONTH_DAY_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
HEAT_PUMP_NAME_TOKENS = {"hp", "wp"}
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


def _number(
    minimum: float, maximum: float, step: float, unit: str | None = None
) -> NumberSelector:
    """Return a number box selector."""
    config: dict[str, Any] = {"min": minimum, "max": maximum, "step": step, "mode": NumberSelectorMode.BOX}
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
            if tokens & HEAT_PUMP_NAME_TOKENS or any(part in haystack for part in HEAT_PUMP_NAME_PARTS):
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
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, KIND_DEFAULTS[kind].name)): TextSelector(),
            vol.Required(CONF_KIND, default=kind): _select(GENERATOR_KINDS, "generator_kind"),
            vol.Required(CONF_ROLE, default=defaults.get(CONF_ROLE, KIND_DEFAULTS[kind].role)): _select(
                ROLES, "generator_role"
            ),
        }
    )


def generator_details_schema(kind: str, role: str, defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for CONFIG_FLOW 4.2-4.5: sensors, conversion, DHW and pricing sections."""
    fields: dict[Any, Any] = {}
    if kind == KIND_HEAT_PUMP:
        fields[vol.Optional(CONF_THERMAL_ENTITY, description=_suggested(defaults.get(CONF_THERMAL_ENTITY)))] = _entity(["energy"])
        fields[vol.Optional(CONF_ELECTRIC_ENTITY, description=_suggested(defaults.get(CONF_ELECTRIC_ENTITY)))] = _entity(["energy"])
        if role == ROLE_BOTH:
            fields[vol.Optional(CONF_DHW_ENTITY, description=_suggested(defaults.get(CONF_DHW_ENTITY)))] = _entity(["energy"])
            fields[vol.Optional(CONF_DHW_ELECTRIC_ENTITY, description=_suggested(defaults.get(CONF_DHW_ELECTRIC_ENTITY)))] = _entity(["energy"])
    else:
        device_class: list[str] | None
        if kind == KIND_GAS_BOILER:
            device_class = ["gas"]
        elif kind == KIND_OTHER:
            device_class = None
        else:
            device_class = ["energy"]
        fields[vol.Required(CONF_ENERGY_ENTITY, description=_suggested(defaults.get(CONF_ENERGY_ENTITY)))] = _entity(device_class)
        if kind in (KIND_GAS_BOILER, KIND_DISTRICT_HEAT) and role == ROLE_BOTH:
            fields[vol.Optional(CONF_DHW_ENTITY, description=_suggested(defaults.get(CONF_DHW_ENTITY)))] = _entity(["energy"])

    conversion: dict[Any, Any] = {}
    if kind == KIND_GAS_BOILER:
        conversion[vol.Required(CONF_HEATING_VALUE, default=defaults.get(CONF_HEATING_VALUE, HEATING_VALUE_HS))] = _select(HEATING_VALUE_OPTIONS, "heating_value")
        conversion[vol.Optional(CONF_HEATING_VALUE_CUSTOM, description=_suggested(defaults.get(CONF_HEATING_VALUE_CUSTOM)))] = _number(5.0, 15.0, 0.001, "kWh/m³")
        conversion[vol.Required(CONF_EFFICIENCY, default=defaults.get(CONF_EFFICIENCY, DEFAULT_GAS_EFFICIENCY))] = _number(0.5, 1.1, 0.01)
    elif kind == KIND_HEAT_PUMP:
        conversion[vol.Required(CONF_CONVERSION_MODE, default=defaults.get(CONF_CONVERSION_MODE, CONVERSION_AUTO))] = _select(HEAT_PUMP_CONVERSION_MODES, "conversion_mode")
        conversion[vol.Required(CONF_SCOP, default=defaults.get(CONF_SCOP, DEFAULT_SCOP))] = _number(1.0, 7.0, 0.1)
    elif kind == KIND_AIR_TO_AIR:
        conversion[vol.Required(CONF_COP, default=defaults.get(CONF_COP, DEFAULT_COP_AIR_TO_AIR))] = _number(1.0, 7.0, 0.1)
    elif kind == KIND_DISTRICT_HEAT:
        conversion[vol.Required(CONF_EFFICIENCY, default=defaults.get(CONF_EFFICIENCY, DEFAULT_DISTRICT_EFFICIENCY))] = _number(0.5, 1.1, 0.01)
    elif kind == KIND_OTHER:
        conversion[vol.Required(CONF_FACTOR, default=defaults.get(CONF_FACTOR, DEFAULT_FACTOR))] = _number(0.001, 1000.0, 0.001)
    if conversion:
        fields[vol.Required(SECTION_CONVERSION)] = section(vol.Schema(conversion), {"collapsed": False})

    if role == ROLE_BOTH:
        dhw_default = defaults.get(CONF_DHW_MODE) or (
            DHW_MEASURED if defaults.get(CONF_DHW_ENTITY) else DHW_BASELINE
        )
        dhw = {
            vol.Required(CONF_DHW_MODE, default=dhw_default): _select(DHW_MODES, "dhw_mode"),
            vol.Optional(CONF_DHW_FIXED_PER_DAY, description=_suggested(defaults.get(CONF_DHW_FIXED_PER_DAY))): _number(0.0, 1000.0, 0.01),
        }
        fields[vol.Required(SECTION_DHW)] = section(vol.Schema(dhw), {"collapsed": False})

    pricing = {
        vol.Optional(CONF_PRICE_ENTITY, description=_suggested(defaults.get(CONF_PRICE_ENTITY))): _entity(),
        vol.Required(CONF_CO2_FACTOR, default=defaults.get(CONF_CO2_FACTOR, KIND_DEFAULTS[kind].co2_factor)): _number(0.0, 10.0, 0.001),
    }
    fields[vol.Required(SECTION_PRICING)] = section(vol.Schema(pricing), {"collapsed": True})
    return vol.Schema(fields)


def flatten_sections(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Merge section dicts of a submitted form into one flat dict."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in (SECTION_CONVERSION, SECTION_DHW, SECTION_PRICING, SECTION_ADVANCED, SECTION_PBL, SECTION_FIT) and isinstance(value, Mapping):
            flat.update(value)
        else:
            flat[key] = value
    return flat


@callback
def validate_generator_details(hass: HomeAssistant, kind: str, role: str, data: Mapping[str, Any]) -> dict[str, str]:
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
    if data.get(CONF_DHW_ENTITY) and (error := _validate_cumulative_entity(hass, data[CONF_DHW_ENTITY], HEAT_UNITS)):
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
        vol.Required(CONF_CLASSIC_BASE_TEMP, default=defaults.get(CONF_CLASSIC_BASE_TEMP, DEFAULT_CLASSIC_BASE_TEMP)): _number(5.0, 25.0, 0.1, "°C"),
        vol.Required(CONF_CLASSIC_HEATING_LIMIT, default=defaults.get(CONF_CLASSIC_HEATING_LIMIT, DEFAULT_CLASSIC_HEATING_LIMIT)): _number(5.0, 25.0, 0.1, "°C"),
        vol.Required(CONF_PBL_PARAMETER_SET, default=defaults.get(CONF_PBL_PARAMETER_SET, "practical")): _select(PBL_PARAMETER_SETS, "pbl_parameter_set"),
        vol.Required(CONF_PBL_WIND_MODE, default=defaults.get(CONF_PBL_WIND_MODE, "linear")): _select(PBL_WIND_MODES, "pbl_wind_mode"),
        vol.Required(CONF_PBL_INCLUDE_SUN, default=defaults.get(CONF_PBL_INCLUDE_SUN, False)): BooleanSelector(),
        vol.Required(CONF_HOUSE_FIT_WIND, default=defaults.get(CONF_HOUSE_FIT_WIND, True)): BooleanSelector(),
    }
    return vol.Schema(
        {
            vol.Required(CONF_SEASON_START, default=defaults.get(CONF_SEASON_START, SEASON_START_OCTOBER)): _select(SEASON_STARTS, "season_start"),
            vol.Required(CONF_METHODS_ENABLED, default=list(defaults.get(CONF_METHODS_ENABLED, DEFAULT_METHODS_ENABLED))): _select(METHODS, "method", multiple=True),
            vol.Required(CONF_METHODS_PRIMARY, default=defaults.get(CONF_METHODS_PRIMARY, DEFAULT_METHOD_PRIMARY)): _select(METHODS, "method"),
            vol.Required(CONF_CLASSIC_WEIGHTED, default=defaults.get(CONF_CLASSIC_WEIGHTED, True)): BooleanSelector(),
            vol.Required(SECTION_ADVANCED): section(vol.Schema(advanced), {"collapsed": True}),
        }
    )


def dhw_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Schema for CONFIG_FLOW step 5 (site-level DHW defaults)."""
    return vol.Schema(
        {
            vol.Required(CONF_DHW_OVERRIDE, default=defaults.get(CONF_DHW_OVERRIDE, DHW_OVERRIDE_KEEP)): _select(DHW_OVERRIDE_OPTIONS, "dhw_override"),
            vol.Required(CONF_SUMMER_START, default=defaults.get(CONF_SUMMER_START, DEFAULT_SUMMER_START)): TextSelector(),
            vol.Required(CONF_SUMMER_END, default=defaults.get(CONF_SUMMER_END, DEFAULT_SUMMER_END)): TextSelector(),
        }
    )


def history_schema(defaults: Mapping[str, Any], *, options: bool) -> vol.Schema:
    """Schema for CONFIG_FLOW step 7; the options variant adds "recompute from"."""
    fields: dict[Any, Any] = {
        vol.Required(CONF_BACKFILL_YEARS, default=defaults.get(CONF_BACKFILL_YEARS, DEFAULT_BACKFILL_YEARS)): _number(0, 10, 1),
        vol.Required(CONF_CLIMATOLOGY_YEARS, default=defaults.get(CONF_CLIMATOLOGY_YEARS, DEFAULT_CLIMATOLOGY_YEARS)): _number(10, 30, 1),
    }
    if options:
        fields[vol.Optional(CONF_RECOMPUTE_FROM)] = DateSelector()
    else:
        fields[vol.Required(CONF_IMPORT_NOW, default=False)] = BooleanSelector()
    return vol.Schema(fields)


def _validate_month_day(value: str) -> bool:
    """Return True when value is a valid MM-DD string."""
    return bool(MONTH_DAY_RE.match(value.strip()))


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
        }

    # --- step 1: site ------------------------------------------------------------------

    async def _async_site_schema(self, defaults: Mapping[str, Any]) -> vol.Schema:
        """Return the site schema with HA home location as defaults."""
        timezones = await _async_timezones(self.hass)
        default_tz = defaults.get(CONF_TIMEZONE, self.hass.config.time_zone)
        if default_tz not in timezones:
            timezones = sorted([*timezones, default_tz])
        location = defaults.get(CONF_LOCATION) or {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
        }
        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, self.hass.config.location_name or DEFAULT_SITE_NAME)): TextSelector(),
                vol.Required(
                    CONF_LOCATION,
                    default={
                        CONF_LATITUDE: location[CONF_LATITUDE],
                        CONF_LONGITUDE: location[CONF_LONGITUDE],
                    },
                ): LocationSelector(LocationSelectorConfig(radius=False)),
                vol.Required(CONF_TIMEZONE, default=default_tz): SelectSelector(
                    SelectSelectorConfig(options=timezones, mode=SelectSelectorMode.DROPDOWN, sort=False)
                ),
                vol.Required(CONF_COUNTRY, default=defaults.get(CONF_COUNTRY, self.hass.config.country or "NL")): CountrySelector(),
            }
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: site name, location, time zone and country."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            site_id = slugify(name)
            if not name or not site_id:
                errors[CONF_NAME] = "invalid_name"
            elif any(
                entry.data.get(CONF_SITE_ID) == site_id or entry.title == name
                for entry in self._async_current_entries()
            ):
                errors[CONF_NAME] = "name_exists"
            elif dt_util.get_time_zone(user_input[CONF_TIMEZONE]) is None:
                errors[CONF_TIMEZONE] = "invalid_timezone"
            if not errors:
                await self.async_set_unique_id(site_id)
                self._abort_if_unique_id_configured()
                location = user_input[CONF_LOCATION]
                self._site = {
                    CONF_SITE_ID: site_id,
                    CONF_NAME: name,
                    CONF_LATITUDE: float(location[CONF_LATITUDE]),
                    CONF_LONGITUDE: float(location[CONF_LONGITUDE]),
                    CONF_TIMEZONE: user_input[CONF_TIMEZONE],
                    CONF_COUNTRY: user_input[CONF_COUNTRY],
                }
                return await self._async_step_weather()
        return self.async_show_form(
            step_id="user",
            data_schema=await self._async_site_schema(user_input or {}),
            errors=errors,
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

    async def async_step_weather_nl(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
                self._site[CONF_WEATHER] = {**weather, CONF_HA_ENTITIES: current.get(CONF_HA_ENTITIES, {})}
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
                vol.Required(CONF_PROVIDER, default=current.get(CONF_PROVIDER, PROVIDER_KNMI)): _select(PROVIDERS_NL, "provider"),
                vol.Required(CONF_STATION_ID, default=current.get(CONF_STATION_ID, nearest)): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(CONF_FALLBACK, default=current.get(CONF_FALLBACK, PROVIDER_OPEN_METEO)): _select(FALLBACKS, "fallback"),
            }
        )
        nearest_name = KNMI_STATIONS[nearest][0]
        return self.async_show_form(
            step_id="weather_nl",
            data_schema=schema,
            errors=errors,
            description_placeholders={"nearest": f"{nearest_name} ({nearest})"},
        )

    async def async_step_weather_intl(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2b: weather source outside the Netherlands."""
        errors: dict[str, str] = {}
        current = self._site.get(CONF_WEATHER, {})
        if user_input is not None:
            weather = {CONF_PROVIDER: user_input[CONF_PROVIDER], CONF_FALLBACK: "none"}
            if weather[CONF_PROVIDER] == PROVIDER_HA_SENSORS:
                self._site[CONF_WEATHER] = {**weather, CONF_HA_ENTITIES: current.get(CONF_HA_ENTITIES, {})}
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
                vol.Required(CONF_PROVIDER, default=current.get(CONF_PROVIDER, PROVIDER_OPEN_METEO)): _select(PROVIDERS_INTL, "provider"),
            }
        )
        return self.async_show_form(step_id="weather_intl", data_schema=schema, errors=errors)

    async def async_step_weather_sensors(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2c: weather from Home Assistant sensors (needs long-term statistics)."""
        errors: dict[str, str] = {}
        current = self._site.get(CONF_WEATHER, {}).get(CONF_HA_ENTITIES, {})
        if user_input is not None:
            for key in (CONF_TEMPERATURE_ENTITY, CONF_WIND_ENTITY, CONF_RADIATION_ENTITY):
                if user_input.get(key) and (error := _validate_measurement_entity(self.hass, user_input[key])):
                    errors[key] = error
            if not errors:
                self._site[CONF_WEATHER] = {
                    **self._site.get(CONF_WEATHER, {}),
                    CONF_PROVIDER: PROVIDER_HA_SENSORS,
                    CONF_HA_ENTITIES: {
                        key: user_input[key]
                        for key in (CONF_TEMPERATURE_ENTITY, CONF_WIND_ENTITY, CONF_RADIATION_ENTITY)
                        if user_input.get(key)
                    },
                }
                return await self._async_after_weather()
        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_ENTITY, description=_suggested(current.get(CONF_TEMPERATURE_ENTITY))): _entity(["temperature"]),
                vol.Optional(CONF_WIND_ENTITY, description=_suggested(current.get(CONF_WIND_ENTITY))): _entity(["wind_speed"]),
                vol.Optional(CONF_RADIATION_ENTITY, description=_suggested(current.get(CONF_RADIATION_ENTITY))): _entity(["irradiance"]),
            }
        )
        return self.async_show_form(step_id="weather_sensors", data_schema=schema, errors=errors)

    # --- step 3: situation -------------------------------------------------------------

    async def async_step_situation(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_generator(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_generator_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
                self._generators.append(normalize_generator(self.hass, self._current, flat, existing))
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

    async def async_step_generator_more(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask whether another generator should be added."""
        return self.async_show_menu(
            step_id="generator_more",
            menu_options=["generator", "dhw"],
            description_placeholders={
                "generators": ", ".join(generator[CONF_NAME] for generator in self._generators) or "-"
            },
        )

    # --- step 5: DHW ---------------------------------------------------------------------

    def _dhw_summary(self) -> str:
        """Return a short per-generator DHW summary for the description."""
        parts = []
        for generator in self._generators:
            mode = generator.get(CONF_DHW_MODE, "-" if generator[CONF_ROLE] != ROLE_BOTH else DHW_BASELINE)
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

    async def async_step_methods(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
        return self.async_show_form(step_id="methods", data_schema=methods_schema(defaults), errors=errors)

    # --- step 7: history ---------------------------------------------------------------

    async def async_step_history(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_summary(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
            station = KNMI_STATIONS.get(weather[CONF_STATION_ID], (weather[CONF_STATION_ID], 0, 0))[0]
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
                "methods": ", ".join(methods.get(CONF_METHODS_ENABLED, [])) + f" (primary {methods.get(CONF_METHODS_PRIMARY, '-')})",
                "season": str(methods.get(CONF_SEASON_START, SEASON_START_OCTOBER)),
                "backfill": str(history.get(CONF_BACKFILL_YEARS, DEFAULT_BACKFILL_YEARS)),
            },
            last_step=True,
        )

    # --- reconfigure -------------------------------------------------------------------

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Reconfigure location and time zone, then the weather source."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
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
                }
                return await self._async_step_weather()
        self._site = dict(entry.data)
        timezones = await _async_timezones(self.hass)
        current_tz = entry.data.get(CONF_TIMEZONE, self.hass.config.time_zone)
        if current_tz not in timezones:
            timezones = sorted([*timezones, current_tz])
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCATION,
                    default={CONF_LATITUDE: entry.data[CONF_LATITUDE], CONF_LONGITUDE: entry.data[CONF_LONGITUDE]},
                ): LocationSelector(LocationSelectorConfig(radius=False)),
                vol.Required(CONF_TIMEZONE, default=current_tz): SelectSelector(
                    SelectSelectorConfig(options=timezones, mode=SelectSelectorMode.DROPDOWN, sort=False)
                ),
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

    async def async_step_reconfigure_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm that the weather history is refetched and all records recomputed."""
        if user_input is not None:
            self._reconfigure_confirmed = True
            return await self._async_finish_reconfigure()
        return self.async_show_form(step_id="reconfigure_confirm", data_schema=vol.Schema({}))


# --------------------------------------------------------------------------------
# Options flow
# --------------------------------------------------------------------------------


class HeatprintOptionsFlow(OptionsFlow):
    """Options: methods, DHW, history, pricing, integrations, advanced."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[OPT_METHODS, OPT_DHW, OPT_HISTORY, OPT_PRICING, OPT_INTEGRATIONS, OPT_ADVANCED],
        )

    def _section(self, key: str) -> dict[str, Any]:
        """Return the stored values of an options section."""
        return dict(self.config_entry.options.get(key, {}))

    def _save(self, key: str, values: Mapping[str, Any]) -> ConfigFlowResult:
        """Store one options section and finish."""
        return self.async_create_entry(data={**self.config_entry.options, key: dict(values)})

    async def async_step_methods(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
        return self.async_show_form(step_id="methods", data_schema=methods_schema(defaults), errors=errors)

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

    async def async_step_history(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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

    async def async_step_pricing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
                vol.Required(CONF_GAS_CO2_FACTOR, default=current.get(CONF_GAS_CO2_FACTOR, DEFAULT_GAS_CO2_KG_PER_M3)): _number(0.0, 10.0, 0.001, "kg/m³"),
                vol.Required(CONF_ELECTRIC_CO2_FACTOR, default=current.get(CONF_ELECTRIC_CO2_FACTOR, DEFAULT_ELECTRIC_CO2_KG_PER_KWH)): _number(0.0, 10.0, 0.001, "kg/kWh"),
                vol.Required(CONF_DISTRICT_CO2_FACTOR, default=current.get(CONF_DISTRICT_CO2_FACTOR, DEFAULT_DISTRICT_CO2_KG_PER_KWH)): _number(0.0, 10.0, 0.001, "kg/kWh"),
                vol.Optional(CONF_CO2_ENTITY, description=_suggested(current.get(CONF_CO2_ENTITY))): _entity(),
            }
        )
        return self.async_show_form(step_id="pricing", data_schema=schema)

    async def async_step_integrations(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """mindergas.nl bridge: token, generator and daily push."""
        current = self._section(OPT_INTEGRATIONS)
        generators = [
            SelectOptionDict(value=subentry.data[CONF_GENERATOR_ID], label=subentry.title)
            for subentry in self.config_entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_GENERATOR
        ]
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_MINDERGAS_TOKEN, "")).strip() or current.get(CONF_MINDERGAS_TOKEN, "")
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
            vol.Optional(CONF_MINDERGAS_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }
        if generators:
            fields[vol.Optional(CONF_MINDERGAS_GENERATOR, description=_suggested(current.get(CONF_MINDERGAS_GENERATOR)))] = SelectSelector(
                SelectSelectorConfig(options=generators, mode=SelectSelectorMode.DROPDOWN)
            )
        fields[vol.Required(CONF_MINDERGAS_DAILY_PUSH, default=current.get(CONF_MINDERGAS_DAILY_PUSH, False))] = BooleanSelector()
        return self.async_show_form(
            step_id="integrations",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={"token_state": "set" if current.get(CONF_MINDERGAS_TOKEN) else "not set"},
        )

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """PBL parameters, wind coefficient, outlier threshold and minimum fit days."""
        current = self._section(OPT_ADVANCED)
        if user_input is not None:
            return self._save(OPT_ADVANCED, flatten_sections(user_input))
        pbl = {
            vol.Required(CONF_PBL_TST_WINTER, default=current.get(CONF_PBL_TST_WINTER, DEFAULT_PBL_TST["winter"])): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(CONF_PBL_TST_SHOULDER, default=current.get(CONF_PBL_TST_SHOULDER, DEFAULT_PBL_TST["shoulder"])): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(CONF_PBL_TST_TRANSITION, default=current.get(CONF_PBL_TST_TRANSITION, DEFAULT_PBL_TST["transition"])): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(CONF_PBL_TST_SUMMER, default=current.get(CONF_PBL_TST_SUMMER, DEFAULT_PBL_TST["summer"])): _number(5.0, 25.0, 0.01, "°C"),
            vol.Required(CONF_PBL_RER_WINTER, default=current.get(CONF_PBL_RER_WINTER, DEFAULT_PBL_RER["winter"])): _number(0.1, 2.0, 0.01),
            vol.Required(CONF_PBL_RER_SHOULDER, default=current.get(CONF_PBL_RER_SHOULDER, DEFAULT_PBL_RER["shoulder"])): _number(0.1, 2.0, 0.01),
            vol.Required(CONF_PBL_RER_TRANSITION, default=current.get(CONF_PBL_RER_TRANSITION, DEFAULT_PBL_RER["transition"])): _number(0.1, 2.0, 0.01),
            vol.Required(CONF_PBL_RER_SUMMER, default=current.get(CONF_PBL_RER_SUMMER, DEFAULT_PBL_RER["summer"])): _number(0.1, 2.0, 0.01),
            vol.Required(CONF_PBL_TOP, default=current.get(CONF_PBL_TOP, DEFAULT_PBL_TOP)): _number(0.0, 5.0, 0.01),
            vol.Required(CONF_PBL_WIND_SQRT_COEF, default=current.get(CONF_PBL_WIND_SQRT_COEF, round(DEFAULT_PBL_WIND_SQRT_COEF, 3))): _number(0.0, 10.0, 0.001),
        }
        fit = {
            vol.Required(CONF_OUTLIER_THRESHOLD, default=current.get(CONF_OUTLIER_THRESHOLD, DEFAULT_OUTLIER_THRESHOLD)): _number(2.0, 10.0, 0.1),
            vol.Required(CONF_MIN_FIT_DAYS, default=current.get(CONF_MIN_FIT_DAYS, DEFAULT_MIN_FIT_DAYS)): _number(15, 120, 1),
        }
        schema = vol.Schema(
            {
                vol.Required(SECTION_PBL): section(vol.Schema(pbl), {"collapsed": True}),
                vol.Required(SECTION_FIT): section(vol.Schema(fit), {"collapsed": False}),
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)


# --------------------------------------------------------------------------------
# Subentry flows
# --------------------------------------------------------------------------------


class _SubentryFlowBase(ConfigSubentryFlow):
    """Shared helpers for the subentry flows (compatible with HA 2025.3 and newer)."""

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

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
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
                    title=generator[CONF_NAME], data=generator, unique_id=generator[CONF_GENERATOR_ID]
                )
        return self.async_show_form(
            step_id="details",
            data_schema=generator_details_schema(kind, role, defaults),
            errors=errors,
            description_placeholders={"name": self._base[CONF_NAME]},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Change name, kind and role of an existing generator."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            self._base = {**subentry.data, **user_input}
            return await self.async_step_reconfigure_details()
        return self.async_show_form(step_id="reconfigure", data_schema=generator_base_schema(subentry.data))

    async def async_step_reconfigure_details(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
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
                    self.hass, self._base, flat, set(), keep_id=str(subentry.data[CONF_GENERATOR_ID])
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
            vol.Required(CONF_DATE, default=defaults.get(CONF_DATE, dt_util.now().date().isoformat())): DateSelector(),
            vol.Required(CONF_CATEGORY, default=defaults.get(CONF_CATEGORY, "insulation")): _select(MEASURE_CATEGORIES, "measure_category"),
            vol.Optional(CONF_NOTES, description=_suggested(defaults.get(CONF_NOTES))): TextSelector(TextSelectorConfig(multiline=True)),
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
        return self.async_show_form(step_id="user", data_schema=measure_schema(user_input or {}), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
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
                return self.async_update_and_abort(self._config_entry, subentry, data=data, title=name)
        return self.async_show_form(
            step_id="reconfigure", data_schema=measure_schema(user_input or subentry.data), errors=errors
        )
