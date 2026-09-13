"""Constants for the Heatprint integration."""

from __future__ import annotations

from datetime import time
from typing import Final, NamedTuple

from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfVolume,
)

DOMAIN: Final = "heatprint"
MANUFACTURER: Final = "Heatprint"
MODEL_SITE: Final = "Site"
PLATFORMS: Final[list[Platform]] = [Platform.SENSOR, Platform.BINARY_SENSOR]

SUBENTRY_TYPE_GENERATOR: Final = "generator"
SUBENTRY_TYPE_MEASURE: Final = "measure"

# Daily processing runs at 06:15 local time: KNMI publishes the definitive day
# values of "yesterday" in the early morning and the recorder has compiled the
# hourly statistics of the previous day by then.
DAILY_RUN_TIME: Final = time(hour=6, minute=15)

BACKFILL_CHUNK_DAYS: Final = 90
WEATHER_CACHE_DAYS: Final = 400
MAX_STORED_FITS: Final = 20
DEFAULT_MIN_FIT_DAYS: Final = 30
FIT_REFRESH_DAYS: Final = 7
DATA_GAP_DAYS: Final = 3
DATA_QUALITY_WINDOW_DAYS: Final = 30
DEFAULT_OUTLIER_THRESHOLD: Final = 4.0

STORAGE_VERSION: Final = 1
STORAGE_KEY_TEMPLATE: Final = "heatprint.{entry_id}"

NOTIFICATION_BACKFILL: Final = "heatprint_backfill_{entry_id}"
NOTIFICATION_IMPORT_HINT: Final = "heatprint_import_hint_{entry_id}"

# --- Site (config entry data) ---------------------------------------------------
CONF_SITE_ID: Final = "site_id"
CONF_NAME: Final = "name"
CONF_LOCATION: Final = "location"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_TIMEZONE: Final = "timezone"
CONF_COUNTRY: Final = "country"
CONF_WEATHER: Final = "weather"
CONF_PROVIDER: Final = "provider"
CONF_STATION_ID: Final = "station_id"
CONF_FALLBACK: Final = "fallback"
CONF_HA_ENTITIES: Final = "ha_entities"
CONF_TEMPERATURE_ENTITY: Final = "temperature"
CONF_WIND_ENTITY: Final = "wind"
CONF_RADIATION_ENTITY: Final = "radiation"
CONF_SITUATION: Final = "situation"

DEFAULT_SITE_NAME: Final = "Home"

# --- Options sections (config entry options) --------------------------------------
OPT_METHODS: Final = "methods"
OPT_DHW: Final = "dhw"
OPT_HISTORY: Final = "history"
OPT_PRICING: Final = "pricing"
OPT_INTEGRATIONS: Final = "integrations"
OPT_ADVANCED: Final = "advanced"

# Methods and season
CONF_SEASON_START: Final = "season_start"
CONF_METHODS_ENABLED: Final = "enabled"
CONF_METHODS_PRIMARY: Final = "primary"
CONF_CLASSIC_WEIGHTED: Final = "classic_weighted"
CONF_CLASSIC_BASE_TEMP: Final = "classic_base_temp"
CONF_CLASSIC_HEATING_LIMIT: Final = "classic_heating_limit"
CONF_PBL_PARAMETER_SET: Final = "pbl_parameter_set"
CONF_PBL_WIND_MODE: Final = "pbl_wind_mode"
CONF_PBL_INCLUDE_SUN: Final = "pbl_include_sun"
CONF_HOUSE_FIT_WIND: Final = "house_fit_wind"
SECTION_ADVANCED: Final = "advanced"

# DHW (domestic hot water and cooking)
CONF_DHW_MODE: Final = "dhw_mode"
CONF_DHW_FIXED_PER_DAY: Final = "dhw_fixed_per_day"
CONF_SUMMER_START: Final = "summer_start"
CONF_SUMMER_END: Final = "summer_end"
CONF_DHW_OVERRIDE: Final = "dhw_override"

# History
CONF_BACKFILL_YEARS: Final = "backfill_years"
CONF_CLIMATOLOGY_YEARS: Final = "climatology_years"
CONF_IMPORT_NOW: Final = "import_now"
CONF_RECOMPUTE_FROM: Final = "recompute_from"

# Pricing and CO2
CONF_GAS_CO2_FACTOR: Final = "gas_co2_factor"
CONF_ELECTRIC_CO2_FACTOR: Final = "electric_co2_factor"
CONF_DISTRICT_CO2_FACTOR: Final = "district_co2_factor"
CONF_CO2_ENTITY: Final = "co2_entity"

# Integrations (mindergas.nl bridge)
CONF_MINDERGAS_TOKEN: Final = "mindergas_token"
CONF_MINDERGAS_GENERATOR: Final = "mindergas_generator_id"
CONF_MINDERGAS_DAILY_PUSH: Final = "mindergas_daily_push"

# Advanced
CONF_PBL_TST_WINTER: Final = "pbl_tst_winter"
CONF_PBL_TST_SHOULDER: Final = "pbl_tst_shoulder"
CONF_PBL_TST_TRANSITION: Final = "pbl_tst_transition"
CONF_PBL_TST_SUMMER: Final = "pbl_tst_summer"
CONF_PBL_RER_WINTER: Final = "pbl_rer_winter"
CONF_PBL_RER_SHOULDER: Final = "pbl_rer_shoulder"
CONF_PBL_RER_TRANSITION: Final = "pbl_rer_transition"
CONF_PBL_RER_SUMMER: Final = "pbl_rer_summer"
CONF_PBL_TOP: Final = "pbl_top"
CONF_PBL_WIND_SQRT_COEF: Final = "pbl_wind_sqrt_coef"
CONF_OUTLIER_THRESHOLD: Final = "outlier_threshold"
CONF_MIN_FIT_DAYS: Final = "min_fit_days"
SECTION_PBL: Final = "pbl"
SECTION_FIT: Final = "fit"

# --- Generator (subentry data) -------------------------------------------------
CONF_GENERATOR_ID: Final = "generator_id"
CONF_KIND: Final = "kind"
CONF_ROLE: Final = "role"
CONF_ENERGY_ENTITY: Final = "energy_entity"
CONF_UNIT: Final = "unit"
CONF_THERMAL_ENTITY: Final = "thermal_entity"
CONF_ELECTRIC_ENTITY: Final = "electric_entity"
CONF_DHW_ENTITY: Final = "dhw_entity"
CONF_DHW_ELECTRIC_ENTITY: Final = "dhw_electric_entity"
CONF_CONVERSION_MODE: Final = "conversion_mode"
CONF_EFFICIENCY: Final = "efficiency"
CONF_HEATING_VALUE: Final = "heating_value"
CONF_HEATING_VALUE_CUSTOM: Final = "heating_value_custom"
CONF_SCOP: Final = "scop"
CONF_COP: Final = "cop"
CONF_FACTOR: Final = "factor"
CONF_PRICE_ENTITY: Final = "price_entity"
CONF_CO2_FACTOR: Final = "co2_factor"
SECTION_CONVERSION: Final = "conversion"
SECTION_DHW: Final = "dhw"
SECTION_PRICING: Final = "pricing"

# --- Measure (subentry data) ---------------------------------------------------
CONF_MEASURE_ID: Final = "measure_id"
CONF_DATE: Final = "date"
CONF_CATEGORY: Final = "category"
CONF_NOTES: Final = "notes"

# --- Enumerations (string lists for selectors) ---------------------------------
PROVIDER_KNMI: Final = "knmi"
PROVIDER_OPEN_METEO: Final = "open_meteo"
PROVIDER_HA_SENSORS: Final = "ha_sensors"
PROVIDERS_NL: Final = [PROVIDER_KNMI, PROVIDER_OPEN_METEO, PROVIDER_HA_SENSORS]
PROVIDERS_INTL: Final = [PROVIDER_OPEN_METEO, PROVIDER_HA_SENSORS]
FALLBACK_NONE: Final = "none"
FALLBACKS: Final = [PROVIDER_OPEN_METEO, FALLBACK_NONE]

SITUATION_GAS: Final = "gas"
SITUATION_HYBRID: Final = "hybrid"
SITUATION_ALL_ELECTRIC: Final = "all_electric"
SITUATION_DISTRICT_HEAT: Final = "district_heat"
SITUATION_CUSTOM: Final = "custom"
SITUATIONS: Final = [
    SITUATION_GAS,
    SITUATION_HYBRID,
    SITUATION_ALL_ELECTRIC,
    SITUATION_DISTRICT_HEAT,
    SITUATION_CUSTOM,
]

KIND_GAS_BOILER: Final = "gas_boiler"
KIND_HEAT_PUMP: Final = "heat_pump"
KIND_ELECTRIC_HEATER: Final = "electric_heater"
KIND_AIR_TO_AIR: Final = "air_to_air"
KIND_DISTRICT_HEAT: Final = "district_heat"
KIND_OTHER: Final = "other"
GENERATOR_KINDS: Final = [
    KIND_GAS_BOILER,
    KIND_HEAT_PUMP,
    KIND_ELECTRIC_HEATER,
    KIND_AIR_TO_AIR,
    KIND_DISTRICT_HEAT,
    KIND_OTHER,
]
HEAT_PUMP_KINDS: Final = frozenset({KIND_HEAT_PUMP, KIND_AIR_TO_AIR})

ROLE_SPACE: Final = "space"
ROLE_DHW: Final = "dhw"
ROLE_BOTH: Final = "both"
ROLES: Final = [ROLE_SPACE, ROLE_DHW, ROLE_BOTH]

UNIT_M3: Final = "m3"
UNIT_KWH: Final = "kwh"
UNIT_GJ: Final = "gj"
CARRIER_UNITS: Final = [UNIT_M3, UNIT_KWH, UNIT_GJ]

CONVERSION_FIXED_EFFICIENCY: Final = "fixed_efficiency"
CONVERSION_MEASURED_THERMAL: Final = "measured_thermal"
CONVERSION_COP_FIXED: Final = "cop_fixed"
CONVERSION_COP_CURVE: Final = "cop_curve"
CONVERSION_FACTOR: Final = "factor"
CONVERSION_AUTO: Final = "auto"
CONVERSION_MODES: Final = [
    CONVERSION_FIXED_EFFICIENCY,
    CONVERSION_MEASURED_THERMAL,
    CONVERSION_COP_FIXED,
    CONVERSION_COP_CURVE,
    CONVERSION_FACTOR,
]
HEAT_PUMP_CONVERSION_MODES: Final = [
    CONVERSION_AUTO,
    CONVERSION_MEASURED_THERMAL,
    CONVERSION_COP_FIXED,
]

HEATING_VALUE_HS: Final = "hs"
HEATING_VALUE_HI: Final = "hi"
HEATING_VALUE_CUSTOM: Final = "custom"
HEATING_VALUE_OPTIONS: Final = [HEATING_VALUE_HS, HEATING_VALUE_HI, HEATING_VALUE_CUSTOM]
HEATING_VALUES_KWH_PER_M3: Final = {HEATING_VALUE_HS: 8.792, HEATING_VALUE_HI: 7.92}

DHW_BASELINE: Final = "baseline"
DHW_FIXED: Final = "fixed"
DHW_MEASURED: Final = "measured"
DHW_NONE: Final = "none"
DHW_MODES: Final = [DHW_BASELINE, DHW_FIXED, DHW_MEASURED, DHW_NONE]
DHW_OVERRIDE_KEEP: Final = "keep"
DHW_OVERRIDE_OPTIONS: Final = [DHW_OVERRIDE_KEEP, *DHW_MODES]
DEFAULT_SUMMER_START: Final = "06-01"
DEFAULT_SUMMER_END: Final = "08-31"

METHOD_CLASSIC: Final = "classic"
METHOD_KNMI14: Final = "knmi14"
METHOD_PBL: Final = "pbl"
METHOD_HOUSE: Final = "house"
METHODS: Final = [METHOD_CLASSIC, METHOD_KNMI14, METHOD_PBL, METHOD_HOUSE]
DEFAULT_METHODS_ENABLED: Final = [METHOD_CLASSIC, METHOD_PBL, METHOD_HOUSE]
DEFAULT_METHOD_PRIMARY: Final = METHOD_HOUSE
# Method used for the main sensors while the house fit is not available yet.
FALLBACK_METHOD_PRIMARY: Final = METHOD_PBL

SEASON_START_OCTOBER: Final = "october"
SEASON_START_JANUARY: Final = "january"
SEASON_START_JULY: Final = "july"
SEASON_STARTS: Final = [SEASON_START_OCTOBER, SEASON_START_JANUARY, SEASON_START_JULY]
SEASON_START_DATES: Final[dict[str, tuple[int, int]]] = {
    SEASON_START_OCTOBER: (10, 1),
    SEASON_START_JANUARY: (1, 1),
    SEASON_START_JULY: (7, 1),
}

PBL_PARAMETER_SETS: Final = ["practical", "optimal"]
PBL_WIND_MODES: Final = ["linear", "sqrt"]
TAC_PRESETS: Final = ["house", "pbl"]

MEASURE_CATEGORIES: Final = ["insulation", "installation", "behaviour", "other"]

PUSH_TARGET_MINDERGAS: Final = "mindergas"
PUSH_TARGETS: Final = [PUSH_TARGET_MINDERGAS]
IMPORT_UNITS: Final = CARRIER_UNITS

# --- Defaults --------------------------------------------------------------------
DEFAULT_CLASSIC_BASE_TEMP: Final = 18.0
DEFAULT_CLASSIC_HEATING_LIMIT: Final = 18.0
DEFAULT_BACKFILL_YEARS: Final = 3
DEFAULT_CLIMATOLOGY_YEARS: Final = 20
DEFAULT_GAS_EFFICIENCY: Final = 0.95
DEFAULT_DISTRICT_EFFICIENCY: Final = 1.0
DEFAULT_SCOP: Final = 3.5
DEFAULT_COP_AIR_TO_AIR: Final = 3.0
DEFAULT_FACTOR: Final = 1.0
DEFAULT_GAS_CO2_KG_PER_M3: Final = 1.78
DEFAULT_ELECTRIC_CO2_KG_PER_KWH: Final = 0.30
DEFAULT_DISTRICT_CO2_KG_PER_KWH: Final = 0.0
GJ_TO_KWH: Final = 277.78

# PBL 2022 "practical" parameter set (METHODS 4.3), overridable in advanced options.
DEFAULT_PBL_TST: Final = {"winter": 17.01, "shoulder": 15.26, "transition": 15.10, "summer": 13.92}
DEFAULT_PBL_RER: Final = {"winter": 1.00, "shoulder": 1.02, "transition": 0.79, "summer": 0.61}
DEFAULT_PBL_TOP: Final = 1.30
DEFAULT_PBL_WIND_SQRT_COEF: Final = 1.0


class KindDefaults(NamedTuple):
    """Per-kind defaults used to prefill generator forms."""

    name: str
    role: str
    conversion_mode: str
    co2_factor: float
    units: frozenset[str]


ENERGY_UNITS: Final = frozenset(
    {
        UnitOfEnergy.KILO_WATT_HOUR,
        UnitOfEnergy.WATT_HOUR,
        UnitOfEnergy.MEGA_WATT_HOUR,
    }
)
HEAT_UNITS: Final = frozenset(
    {
        UnitOfEnergy.KILO_WATT_HOUR,
        UnitOfEnergy.WATT_HOUR,
        UnitOfEnergy.MEGA_WATT_HOUR,
        UnitOfEnergy.GIGA_JOULE,
        UnitOfEnergy.MEGA_JOULE,
    }
)
GAS_UNITS: Final = frozenset({UnitOfVolume.CUBIC_METERS, UnitOfVolume.CUBIC_FEET})

KIND_DEFAULTS: Final[dict[str, KindDefaults]] = {
    KIND_GAS_BOILER: KindDefaults(
        "Gas boiler", ROLE_BOTH, CONVERSION_FIXED_EFFICIENCY, DEFAULT_GAS_CO2_KG_PER_M3, GAS_UNITS
    ),
    KIND_HEAT_PUMP: KindDefaults(
        "Heat pump", ROLE_BOTH, CONVERSION_AUTO, DEFAULT_ELECTRIC_CO2_KG_PER_KWH, ENERGY_UNITS
    ),
    KIND_ELECTRIC_HEATER: KindDefaults(
        "Electric heating",
        ROLE_SPACE,
        CONVERSION_FACTOR,
        DEFAULT_ELECTRIC_CO2_KG_PER_KWH,
        ENERGY_UNITS,
    ),
    KIND_AIR_TO_AIR: KindDefaults(
        "Air-to-air heat pump",
        ROLE_SPACE,
        CONVERSION_COP_FIXED,
        DEFAULT_ELECTRIC_CO2_KG_PER_KWH,
        ENERGY_UNITS,
    ),
    KIND_DISTRICT_HEAT: KindDefaults(
        "District heat",
        ROLE_BOTH,
        CONVERSION_FIXED_EFFICIENCY,
        DEFAULT_DISTRICT_CO2_KG_PER_KWH,
        HEAT_UNITS,
    ),
    KIND_OTHER: KindDefaults("Other heat source", ROLE_SPACE, CONVERSION_FACTOR, 0.0, frozenset()),
}

# Generator drafts prefilled by the "heating situation" wizard step (CONFIG_FLOW step 3).
SITUATION_DRAFTS: Final[dict[str, list[tuple[str, str]]]] = {
    SITUATION_GAS: [(KIND_GAS_BOILER, ROLE_BOTH)],
    SITUATION_HYBRID: [(KIND_GAS_BOILER, ROLE_BOTH), (KIND_HEAT_PUMP, ROLE_SPACE)],
    SITUATION_ALL_ELECTRIC: [(KIND_HEAT_PUMP, ROLE_BOTH)],
    SITUATION_DISTRICT_HEAT: [(KIND_DISTRICT_HEAT, ROLE_BOTH)],
    SITUATION_CUSTOM: [],
}

# --- KNMI automatic weather stations with daily TG/FG/Q data (station, name, lat, lon)
KNMI_STATIONS: Final[dict[str, tuple[str, float, float]]] = {
    "215": ("Voorschoten", 52.141, 4.437),
    "235": ("De Kooy", 52.928, 4.781),
    "240": ("Schiphol", 52.318, 4.790),
    "242": ("Vlieland", 53.241, 4.921),
    "249": ("Berkhout", 52.644, 4.979),
    "251": ("Hoorn Terschelling", 53.392, 5.346),
    "257": ("Wijk aan Zee", 52.506, 4.603),
    "260": ("De Bilt", 52.100, 5.180),
    "267": ("Stavoren", 52.898, 5.384),
    "269": ("Lelystad", 52.458, 5.520),
    "270": ("Leeuwarden", 53.224, 5.752),
    "273": ("Marknesse", 52.703, 5.888),
    "275": ("Deelen", 52.056, 5.873),
    "277": ("Lauwersoog", 53.413, 6.200),
    "278": ("Heino", 52.435, 6.259),
    "279": ("Hoogeveen", 52.750, 6.574),
    "280": ("Eelde", 53.125, 6.585),
    "283": ("Hupsel", 52.069, 6.657),
    "286": ("Nieuw Beerta", 53.196, 7.150),
    "290": ("Twenthe", 52.274, 6.891),
    "310": ("Vlissingen", 51.442, 3.596),
    "319": ("Westdorpe", 51.226, 3.861),
    "323": ("Wilhelminadorp", 51.527, 3.884),
    "330": ("Hoek van Holland", 51.992, 4.122),
    "340": ("Woensdrecht", 51.449, 4.342),
    "344": ("Rotterdam", 51.962, 4.447),
    "348": ("Cabauw", 51.970, 4.926),
    "350": ("Gilze-Rijen", 51.566, 4.936),
    "356": ("Herwijnen", 51.859, 5.146),
    "370": ("Eindhoven", 51.451, 5.377),
    "375": ("Volkel", 51.659, 5.707),
    "377": ("Ell", 51.198, 5.763),
    "380": ("Maastricht", 50.906, 5.762),
    "391": ("Arcen", 51.498, 6.196),
}
DEFAULT_KNMI_STATION: Final = "260"

# --- External statistics (DATA_MODEL 2.2) ----------------------------------------
UNIT_DEGREE_DAYS: Final = UnitOfTemperature.KELVIN  # "K"; HA does not support "°C·d"
UNIT_KWH_PER_K: Final = "kWh/K"
UNIT_M3_PER_K: Final = "m³/K"
UNIT_W_PER_K: Final = "W/K"
UNIT_KWH_PER_DAY: Final = "kWh/d"
UNIT_PERCENT: Final = PERCENTAGE

STATISTIC_MEAN: Final = "mean"
STATISTIC_SUM: Final = "sum"


class MetricDef(NamedTuple):
    """Definition of one external statistic written by Heatprint."""

    key: str
    kind: str  # STATISTIC_MEAN or STATISTIC_SUM
    unit: str
    # HA unit class used for optional display conversion. Degree days use unit "K"
    # but must never be converted like a temperature, hence unit_class None.
    unit_class: str | None


METRIC_T_MEAN: Final = "t_mean"
METRIC_TAC_PBL: Final = "tac_pbl"
METRIC_TAC_HOUSE: Final = "tac_house"
METRIC_DD_CLASSIC: Final = "dd_classic"
METRIC_DD_KNMI14: Final = "dd_knmi14"
METRIC_DD_PBL: Final = "dd_pbl"
METRIC_DD_HOUSE: Final = "dd_house"
METRIC_HEAT_SPACE: Final = "heat_space"
METRIC_HEAT_DHW: Final = "heat_dhw"
METRIC_ELECTRIC_HP: Final = "electric_hp"
METRIC_GAS: Final = "gas"
METRIC_HEAT_GENERATOR_PREFIX: Final = "heat_"
METRIC_HEAT_DHW_GENERATOR_PREFIX: Final = "heat_dhw_"

SITE_METRICS: Final[tuple[MetricDef, ...]] = (
    MetricDef(METRIC_T_MEAN, STATISTIC_MEAN, UnitOfTemperature.CELSIUS, "temperature"),
    MetricDef(METRIC_TAC_PBL, STATISTIC_MEAN, UnitOfTemperature.CELSIUS, "temperature"),
    MetricDef(METRIC_TAC_HOUSE, STATISTIC_MEAN, UnitOfTemperature.CELSIUS, "temperature"),
    MetricDef(METRIC_DD_CLASSIC, STATISTIC_SUM, UNIT_DEGREE_DAYS, None),
    MetricDef(METRIC_DD_KNMI14, STATISTIC_SUM, UNIT_DEGREE_DAYS, None),
    MetricDef(METRIC_DD_PBL, STATISTIC_SUM, UNIT_DEGREE_DAYS, None),
    MetricDef(METRIC_DD_HOUSE, STATISTIC_SUM, UNIT_DEGREE_DAYS, None),
    MetricDef(METRIC_HEAT_SPACE, STATISTIC_SUM, UnitOfEnergy.KILO_WATT_HOUR, "energy"),
    MetricDef(METRIC_HEAT_DHW, STATISTIC_SUM, UnitOfEnergy.KILO_WATT_HOUR, "energy"),
    MetricDef(METRIC_ELECTRIC_HP, STATISTIC_SUM, UnitOfEnergy.KILO_WATT_HOUR, "energy"),
    MetricDef(METRIC_GAS, STATISTIC_SUM, UnitOfVolume.CUBIC_METERS, "volume"),
)
METHOD_TO_DD_METRIC: Final[dict[str, str]] = {
    METHOD_CLASSIC: METRIC_DD_CLASSIC,
    METHOD_KNMI14: METRIC_DD_KNMI14,
    METHOD_PBL: METRIC_DD_PBL,
    METHOD_HOUSE: METRIC_DD_HOUSE,
}


def statistic_id(site_id: str, metric: str) -> str:
    """Return the external statistic id for a site metric: heatprint:<site>_<metric>."""
    return f"{DOMAIN}:{site_id}_{metric}"


def generator_metric(generator_id: str) -> str:
    """Return the metric key for the space heat delivered by one generator."""
    return f"{METRIC_HEAT_GENERATOR_PREFIX}{generator_id}"


def generator_dhw_metric(generator_id: str) -> str:
    """Return the metric key for the DHW heat delivered by one generator."""
    return f"{METRIC_HEAT_DHW_GENERATOR_PREFIX}{generator_id}"


# --- Data quality flags (METHODS 10); order defines the bit in the compact store ---
FLAG_WEATHER_MISSING: Final = "WEATHER_MISSING"
FLAG_WEATHER_PARTIAL: Final = "WEATHER_PARTIAL"
FLAG_WEATHER_PROVISIONAL: Final = "WEATHER_PROVISIONAL"
FLAG_ENERGY_MISSING: Final = "ENERGY_MISSING"
FLAG_PARTIAL_DAY: Final = "PARTIAL_DAY"
FLAG_INTERPOLATED: Final = "INTERPOLATED"
FLAG_METER_RESET: Final = "METER_RESET"
FLAG_HEAT_ESTIMATED: Final = "HEAT_ESTIMATED"
FLAG_HOUSE_NOT_FITTED: Final = "HOUSE_NOT_FITTED"
FLAG_OUTLIER: Final = "OUTLIER"
FLAG_IMPORTED: Final = "IMPORTED"
FLAG_DHW_BASELINE_MISSING: Final = "DHW_BASELINE_MISSING"
FLAG_NAMES: Final[tuple[str, ...]] = (
    FLAG_WEATHER_MISSING,
    FLAG_WEATHER_PARTIAL,
    FLAG_WEATHER_PROVISIONAL,
    FLAG_ENERGY_MISSING,
    FLAG_PARTIAL_DAY,
    FLAG_INTERPOLATED,
    FLAG_METER_RESET,
    FLAG_HEAT_ESTIMATED,
    FLAG_HOUSE_NOT_FITTED,
    FLAG_OUTLIER,
    FLAG_IMPORTED,
    FLAG_DHW_BASELINE_MISSING,
)
FLAG_BITS: Final[dict[str, int]] = {name: 1 << index for index, name in enumerate(FLAG_NAMES)}
# Days carrying one of these flags are excluded from fits and k-values.
EXCLUSION_FLAGS: Final = frozenset(
    {
        FLAG_WEATHER_MISSING,
        FLAG_ENERGY_MISSING,
        FLAG_PARTIAL_DAY,
        FLAG_METER_RESET,
        FLAG_OUTLIER,
    }
)

# --- Services (DATA_MODEL 5) -----------------------------------------------------
SERVICE_IMPORT_READINGS: Final = "import_readings"
SERVICE_RECOMPUTE: Final = "recompute"
SERVICE_FIT_SIGNATURE: Final = "fit_signature"
SERVICE_COMPARE_PERIODS: Final = "compare_periods"
SERVICE_MEASURE_EFFECT: Final = "measure_effect"
SERVICE_FORECAST: Final = "forecast"
SERVICE_EXPORT_DAILY: Final = "export_daily"
SERVICE_PUSH_READING: Final = "push_reading"
SERVICE_CLEAR_STATISTICS: Final = "clear_statistics"

ATTR_ENTRY_ID: Final = "entry_id"
ATTR_GENERATOR_ID: Final = "generator_id"
ATTR_MEASURE_ID: Final = "measure_id"
ATTR_CSV: Final = "csv"
ATTR_PATH: Final = "path"
ATTR_MAPPING: Final = "mapping"
ATTR_DATE_COLUMN: Final = "date_column"
ATTR_READING_COLUMN: Final = "reading_column"
ATTR_DATE_FORMAT: Final = "date_format"
ATTR_DECIMAL: Final = "decimal"
ATTR_DELIMITER: Final = "delimiter"
ATTR_UNIT: Final = "unit"
ATTR_FROM_DATE: Final = "from_date"
ATTR_START: Final = "start"
ATTR_END: Final = "end"
ATTR_SEASON: Final = "season"
ATTR_TAC_PRESET: Final = "tac_preset"
ATTR_FIT_WIND: Final = "fit_wind"
ATTR_BASE_START: Final = "base_start"
ATTR_BASE_END: Final = "base_end"
ATTR_TARGET_START: Final = "target_start"
ATTR_TARGET_END: Final = "target_end"
ATTR_METHOD: Final = "method"
ATTR_TARGET: Final = "target"
ATTR_DATE: Final = "date"

EXPORT_DIRECTORY: Final = "heatprint"

MINDERGAS_API_URL: Final = "https://www.mindergas.nl/api/meter_readings"
MINDERGAS_AUTH_HEADER: Final = "AUTH-TOKEN"

# --- Sensor keys (DATA_MODEL 4) ----------------------------------------------------
SENSOR_EFFECTIVE_TEMPERATURE: Final = "effective_temperature"
SENSOR_DEGREE_DAYS_YESTERDAY: Final = "degree_days_yesterday"
SENSOR_DEGREE_DAYS_SEASON: Final = "degree_days_season"
SENSOR_HEAT_SPACE_YESTERDAY: Final = "heat_space_yesterday"
SENSOR_HEAT_SPACE_SEASON: Final = "heat_space_season"
SENSOR_HEAT_DHW_SEASON: Final = "heat_dhw_season"
SENSOR_HEAT_PER_DEGREE_DAY: Final = "heat_per_degree_day"
SENSOR_GAS_PER_DEGREE_DAY: Final = "gas_per_degree_day"
SENSOR_HEAT_PUMP_SHARE_SEASON: Final = "heat_pump_share_season"
SENSOR_COP_YESTERDAY: Final = "cop_yesterday"
SENSOR_HEAT_LOSS_COEFFICIENT: Final = "heat_loss_coefficient"
SENSOR_BALANCE_TEMPERATURE: Final = "balance_temperature"
SENSOR_FIT_QUALITY: Final = "fit_quality"
SENSOR_FORECAST_HEAT_SEASON: Final = "forecast_heat_season"
SENSOR_FORECAST_GAS_SEASON: Final = "forecast_gas_season"
SENSOR_FORECAST_ELECTRIC_SEASON: Final = "forecast_electric_season"
SENSOR_DHW_BASELINE: Final = "dhw_baseline"
SENSOR_DATA_QUALITY: Final = "data_quality"
SENSOR_LAST_WEATHER_UPDATE: Final = "last_weather_update"
SENSOR_GENERATOR_HEAT_SPACE_SEASON: Final = "generator_heat_space_season"
SENSOR_GENERATOR_HEAT_DHW_SEASON: Final = "generator_heat_dhw_season"
SENSOR_GENERATOR_SHARE_SEASON: Final = "generator_share_season"
BINARY_SENSOR_DATA_GAP: Final = "data_gap"
