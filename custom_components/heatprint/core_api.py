"""Adapters between the Home Assistant shell and the pure-Python heatprint_core.

Every call into heatprint_core lives in this module so the names and signatures
of the core are reconciled in one place. The rest of the integration works with
the plain dataclasses
defined here (``WeatherDay``, ``DailyEnergyInput``, ``DayMetrics``, ...), with
JSON-serialisable dicts (fits, forecasts, climatology) and with opaque core
``DailyRecord`` objects that are only passed back into core analyses.

The core is imported as modules (not names) so that a renamed core function
fails at call time with a clear traceback instead of breaking the import of the
whole integration.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path
from typing import TYPE_CHECKING, Any

# HACS only copies this folder; heatprint_core is bundled here, not on PyPI.
_INTEGRATION_DIR = str(Path(__file__).resolve().parent)
if _INTEGRATION_DIR not in sys.path:
    sys.path.insert(0, _INTEGRATION_DIR)

from aiohttp import ClientError, ClientSession

from heatprint_core import flags as core_flags
from heatprint_core import heat as core_heat
from heatprint_core import models as core_models
from heatprint_core import pipeline as core_pipeline
from heatprint_core import readings as core_readings
from heatprint_core import season as core_season
from heatprint_core.analysis import compare as core_compare
from heatprint_core.analysis import forecast as core_forecast
from heatprint_core.analysis import normalize as core_normalize
from heatprint_core.analysis import signature as core_signature
from heatprint_core.importers import csv_readings as core_csv
from heatprint_core.rooms import allocation as core_rooms
from heatprint_core.rooms import signature as core_room_signature
from heatprint_core.weather import climatology as core_climatology
from heatprint_core.weather import knmi as core_knmi
from heatprint_core.weather import open_meteo as core_open_meteo

from .const import (
    CONF_BACKFILL_YEARS,
    CONF_CATEGORY,
    CONF_CLASSIC_BASE_TEMP,
    CONF_CLASSIC_HEATING_LIMIT,
    CONF_CLASSIC_WEIGHTED,
    CONF_CLIMATOLOGY_YEARS,
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
    CONF_EFFICIENCY,
    CONF_ELECTRIC_ENTITY,
    CONF_ENERGY_ENTITY,
    CONF_FACTOR,
    CONF_FALLBACK,
    CONF_GENERATOR_ID,
    CONF_HA_ENTITIES,
    CONF_HEATING_VALUE,
    CONF_HEATING_VALUE_CUSTOM,
    CONF_HOUSE_FIT_WIND,
    CONF_KIND,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MEASURE_ID,
    CONF_METHODS_ENABLED,
    CONF_METHODS_PRIMARY,
    CONF_MIN_FIT_DAYS,
    CONF_AREA_ID,
    CONF_DEMAND_ENTITY,
    CONF_DEMAND_KIND,
    CONF_EMITTER_KIND,
    CONF_ENABLED,
    CONF_FLOOR_AREA_M2,
    CONF_NAME,
    CONF_NOTES,
    CONF_OUTPUT_W_PER_M2_ELECTRIC,
    CONF_OUTPUT_W_PER_M2_OTHER,
    CONF_OUTPUT_W_PER_M2_RADIATOR,
    CONF_OUTPUT_W_PER_M2_UNDERFLOOR,
    CONF_RATED_OUTPUT_W,
    CONF_ROOM_ID,
    CONF_ROOM_TEMPERATURE_ENTITY,
    CONF_VOLUME_M3,
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
    CONF_ROLE,
    CONF_SCOP,
    CONF_SEASON_START,
    CONF_SITE_ID,
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
    CONVERSION_COP_FIXED,
    CONVERSION_MEASURED_THERMAL,
    DEFAULT_BACKFILL_YEARS,
    DEFAULT_CLASSIC_BASE_TEMP,
    DEFAULT_CLASSIC_HEATING_LIMIT,
    DEFAULT_CLIMATOLOGY_YEARS,
    DEFAULT_COP_AIR_TO_AIR,
    DEFAULT_DISTRICT_EFFICIENCY,
    DEFAULT_FACTOR,
    DEFAULT_GAS_EFFICIENCY,
    DEFAULT_METHOD_PRIMARY,
    DEFAULT_METHODS_ENABLED,
    DEFAULT_MIN_FIT_DAYS,
    DEFAULT_OUTLIER_THRESHOLD,
    DEFAULT_PBL_RER,
    DEFAULT_PBL_TOP,
    DEFAULT_PBL_TST,
    DEFAULT_PBL_WIND_SQRT_COEF,
    DEFAULT_SCOP,
    DEFAULT_SUMMER_END,
    DEFAULT_SUMMER_START,
    DHW_BASELINE,
    DHW_NONE,
    DHW_OVERRIDE_KEEP,
    FALLBACK_NONE,
    FLAG_ENERGY_MISSING,
    FLAG_WEATHER_PROVISIONAL,
    GJ_TO_KWH,
    HEAT_PUMP_KINDS,
    HEATING_VALUE_CUSTOM,
    HEATING_VALUE_HS,
    HEATING_VALUES_KWH_PER_M3,
    KIND_DEFAULTS,
    KIND_DISTRICT_HEAT,
    KIND_ELECTRIC_HEATER,
    KIND_GAS_BOILER,
    KIND_HEAT_PUMP,
    METHOD_CLASSIC,
    METHOD_HOUSE,
    METHOD_KNMI14,
    METHOD_PBL,
    METRIC_DD_CLASSIC,
    METRIC_DD_HOUSE,
    METRIC_DD_KNMI14,
    METRIC_DD_PBL,
    METRIC_ELECTRIC_HP,
    METRIC_GAS,
    METRIC_HEAT_DHW,
    METRIC_HEAT_SPACE,
    METRIC_HEAT_UNALLOCATED,
    METRIC_T_MEAN,
    METRIC_TAC_HOUSE,
    METRIC_TAC_PBL,
    OPT_ADVANCED,
    OPT_DHW,
    OPT_HISTORY,
    OPT_METHODS,
    OPT_ROOMS,
    PROVIDER_HA_SENSORS,
    PROVIDER_KNMI,
    PROVIDER_OPEN_METEO,
    ROLE_BOTH,
    ROLE_DHW,
    SEASON_START_DATES,
    SEASON_START_OCTOBER,
    SUBENTRY_TYPE_GENERATOR,
    SUBENTRY_TYPE_MEASURE,
    SUBENTRY_TYPE_ROOM,
    UNIT_GJ,
    UNIT_KWH,
    UNIT_M3,
    generator_dhw_metric,
    generator_metric,
    room_demand_metric,
    room_heat_metric,
    room_t_mean_metric,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


class CoreError(Exception):
    """Base error raised by the adapter layer."""


class WeatherCannotConnect(CoreError):
    """The weather provider could not be reached."""


class WeatherNoData(CoreError):
    """The weather provider returned no data for the station or location."""


class InsufficientData(CoreError):
    """An analysis has too few usable days."""


# TAC regressor used by the fit per service preset; the core supports the house and
# the PBL effective temperature (heatprint_core.analysis.signature.TAC_KEYS).
TAC_KEY_FOR_PRESET: dict[str, str] = {"house": "tac_house", "pbl": "tac_pbl"}

# Extra key in the stored climatology dict: balance temperature of its house series.
CLIMATOLOGY_BALANCE_KEY = "house_balance_temp"


# --------------------------------------------------------------------------------
# Plain data used by the HA shell
# --------------------------------------------------------------------------------


@dataclass(slots=True)
class WeatherDay:
    """One day of weather input (METHODS 2), independent of core types."""

    date: date
    t_mean: float | None
    wind_mean: float | None = None
    radiation: float | None = None
    t_min: float | None = None
    t_max: float | None = None
    provisional: bool = False
    source: str = ""

    def to_store(self) -> dict[str, Any]:
        """Return a compact JSON representation for the weather cache."""
        return {
            "t": self.t_mean,
            "w": self.wind_mean,
            "q": self.radiation,
            "tn": self.t_min,
            "tx": self.t_max,
            "p": self.provisional,
            "s": self.source,
        }

    @classmethod
    def from_store(cls, day: date, data: Mapping[str, Any]) -> WeatherDay:
        """Rebuild a weather day from the compact store representation."""
        return cls(
            date=day,
            t_mean=data.get("t"),
            wind_mean=data.get("w"),
            radiation=data.get("q"),
            t_min=data.get("tn"),
            t_max=data.get("tx"),
            provisional=bool(data.get("p", False)),
            source=str(data.get("s", "")),
        )


@dataclass(slots=True)
class DailyEnergyInput:
    """Daily consumption of one generator in canonical units (m3 for gas, kWh else)."""

    carrier: float | None = None
    thermal: float | None = None
    electric: float | None = None
    dhw: float | None = None
    dhw_electric: float | None = None
    imported: bool = False


@dataclass(slots=True)
class DayMetrics:
    """Metric values of one day record as written to the external statistics."""

    date: date
    values: dict[str, float | None]
    flags: list[str]
    provisional: bool
    cop: float | None = None
    tac_primary: float | None = None


@dataclass(slots=True)
class GeneratorConfig:
    """Generator configuration as stored in a ``generator`` subentry (flattened)."""

    generator_id: str
    subentry_id: str | None
    name: str
    kind: str
    role: str
    energy_entity: str | None
    unit: str
    thermal_entity: str | None
    electric_entity: str | None
    dhw_entity: str | None
    dhw_electric_entity: str | None
    conversion_mode: str
    efficiency: float
    heating_value_kwh_per_m3: float
    scop: float
    cop: float
    factor: float
    dhw_mode: str
    dhw_fixed_per_day: float | None
    price_entity: str | None
    co2_factor: float

    @property
    def entities(self) -> set[str]:
        """Return all cumulative entities that must be read from the recorder."""
        return {
            entity
            for entity in (
                self.energy_entity,
                self.thermal_entity,
                self.electric_entity,
                self.dhw_entity,
                self.dhw_electric_entity,
            )
            if entity
        }

    @property
    def is_heat_pump(self) -> bool:
        """Return True for heat pump kinds (share and electric_hp statistics)."""
        return self.kind in HEAT_PUMP_KINDS


@dataclass(slots=True)
class MeasureConfig:
    """Measure configuration as stored in a ``measure`` subentry."""

    measure_id: str
    subentry_id: str | None
    name: str
    date: date
    category: str
    notes: str


@dataclass(slots=True)
class RoomConfig:
    """Room configuration as stored in a ``room`` subentry (DATA_MODEL 1.6)."""

    room_id: str
    subentry_id: str | None
    name: str
    area_id: str | None
    demand_entity: str | None
    demand_kind: str
    temperature_entity: str | None
    emitter_kind: str
    rated_output_w: float | None
    floor_area_m2: float | None
    volume_m3: float | None
    price_entity: str | None
    enabled: bool = True

    @property
    def is_metered(self) -> bool:
        """True when the room uses a dedicated energy meter."""
        return self.demand_kind == "metered_energy"

    @property
    def entities(self) -> set[str]:
        """Entities that must be read from the recorder for this room."""
        return {entity for entity in (self.demand_entity, self.temperature_entity) if entity}


@dataclass(slots=True)
class SeasonWindow:
    """A heating season window (start inclusive, end inclusive)."""

    label: str
    start: date
    end: date


# --------------------------------------------------------------------------------
# Config entry -> plain config
# --------------------------------------------------------------------------------


def _month_day_text(value: str | None, default: str) -> str:
    """Return a normalised MM-DD string."""
    text = (value or default).strip()
    month, day = text.split("-", 1)
    return f"{int(month):02d}-{int(day):02d}"


def generator_configs(entry: ConfigEntry) -> list[GeneratorConfig]:
    """Return the generators configured as subentries of the entry."""
    generators: list[GeneratorConfig] = []
    dhw_opts = entry.options.get(OPT_DHW, {})
    override = dhw_opts.get(CONF_DHW_OVERRIDE, DHW_OVERRIDE_KEEP)
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_GENERATOR:
            continue
        data = subentry.data
        kind = data[CONF_KIND]
        role = data.get(CONF_ROLE, ROLE_BOTH)
        heating_value = data.get(CONF_HEATING_VALUE, HEATING_VALUE_HS)
        if heating_value == HEATING_VALUE_CUSTOM:
            hv_kwh_per_m3 = float(
                data.get(CONF_HEATING_VALUE_CUSTOM, HEATING_VALUES_KWH_PER_M3[HEATING_VALUE_HS])
            )
        else:
            hv_kwh_per_m3 = HEATING_VALUES_KWH_PER_M3.get(
                heating_value, HEATING_VALUES_KWH_PER_M3[HEATING_VALUE_HS]
            )
        dhw_mode = data.get(CONF_DHW_MODE, DHW_BASELINE)
        if role == ROLE_BOTH and override != DHW_OVERRIDE_KEEP:
            dhw_mode = override
        if role != ROLE_BOTH:
            dhw_mode = DHW_NONE
        conversion_mode = data.get(CONF_CONVERSION_MODE, CONVERSION_AUTO)
        if kind == KIND_HEAT_PUMP and conversion_mode == CONVERSION_AUTO:
            conversion_mode = (
                CONVERSION_MEASURED_THERMAL
                if data.get(CONF_THERMAL_ENTITY)
                else CONVERSION_COP_FIXED
            )
        unit = data.get(CONF_UNIT, UNIT_M3 if kind == KIND_GAS_BOILER else UNIT_KWH)
        fixed = data.get(CONF_DHW_FIXED_PER_DAY)
        fixed_value = float(fixed) if fixed is not None else None
        co2_factor = float(data.get(CONF_CO2_FACTOR, KIND_DEFAULTS[kind].co2_factor))
        if unit == UNIT_GJ:
            # Recorder reads are normalised to kWh (see recorder_source), so a GJ
            # based fixed DHW amount (GJ/day) and CO2 factor (kg/GJ) are converted
            # to the same canonical unit.
            if fixed_value is not None:
                fixed_value *= GJ_TO_KWH
            co2_factor /= GJ_TO_KWH
        generators.append(
            GeneratorConfig(
                generator_id=data[CONF_GENERATOR_ID],
                subentry_id=subentry.subentry_id,
                name=subentry.title or data.get(CONF_NAME, data[CONF_GENERATOR_ID]),
                kind=kind,
                role=role,
                energy_entity=data.get(CONF_ENERGY_ENTITY) or data.get(CONF_ELECTRIC_ENTITY),
                unit=UNIT_KWH if unit == UNIT_GJ else unit,
                thermal_entity=data.get(CONF_THERMAL_ENTITY),
                electric_entity=data.get(CONF_ELECTRIC_ENTITY),
                dhw_entity=data.get(CONF_DHW_ENTITY),
                dhw_electric_entity=data.get(CONF_DHW_ELECTRIC_ENTITY),
                conversion_mode=conversion_mode,
                efficiency=float(
                    data.get(
                        CONF_EFFICIENCY,
                        DEFAULT_DISTRICT_EFFICIENCY
                        if kind == KIND_DISTRICT_HEAT
                        else DEFAULT_GAS_EFFICIENCY,
                    )
                ),
                heating_value_kwh_per_m3=hv_kwh_per_m3,
                scop=float(data.get(CONF_SCOP, DEFAULT_SCOP)),
                cop=float(data.get(CONF_COP, DEFAULT_COP_AIR_TO_AIR)),
                factor=float(data.get(CONF_FACTOR, DEFAULT_FACTOR)),
                dhw_mode=dhw_mode,
                dhw_fixed_per_day=fixed_value,
                price_entity=data.get(CONF_PRICE_ENTITY),
                co2_factor=co2_factor,
            )
        )
    return generators


def room_configs(entry: ConfigEntry) -> list[RoomConfig]:
    """Return the rooms configured as subentries of the entry."""
    rooms: list[RoomConfig] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_ROOM:
            continue
        data = subentry.data
        rated = data.get(CONF_RATED_OUTPUT_W)
        area = data.get(CONF_FLOOR_AREA_M2)
        volume = data.get(CONF_VOLUME_M3)
        rooms.append(
            RoomConfig(
                room_id=data[CONF_ROOM_ID],
                subentry_id=subentry.subentry_id,
                name=subentry.title or data.get(CONF_NAME, data[CONF_ROOM_ID]),
                area_id=data.get(CONF_AREA_ID),
                demand_entity=data.get(CONF_DEMAND_ENTITY),
                demand_kind=data.get(CONF_DEMAND_KIND, "percentage"),
                temperature_entity=data.get(CONF_ROOM_TEMPERATURE_ENTITY),
                emitter_kind=data.get(CONF_EMITTER_KIND, "radiator"),
                rated_output_w=float(rated) if rated is not None else None,
                floor_area_m2=float(area) if area is not None else None,
                volume_m3=float(volume) if volume is not None else None,
                price_entity=data.get(CONF_PRICE_ENTITY),
                enabled=bool(data.get(CONF_ENABLED, True)),
            )
        )
    return rooms


def rooms_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return the rooms options section with defaults applied."""
    from .first_run import default_rooms_options

    return default_rooms_options(entry.options.get(OPT_ROOMS, {}))


def output_w_per_m2_table(entry: ConfigEntry) -> dict[str, float]:
    """Return the configurable emitter-output table (METHODS 12.2 placeholders)."""
    opts = rooms_options(entry)
    return {
        "radiator": float(opts[CONF_OUTPUT_W_PER_M2_RADIATOR]),
        "underfloor": float(opts[CONF_OUTPUT_W_PER_M2_UNDERFLOOR]),
        "electric": float(opts[CONF_OUTPUT_W_PER_M2_ELECTRIC]),
        "other": float(opts[CONF_OUTPUT_W_PER_M2_OTHER]),
    }


def measure_configs(entry: ConfigEntry) -> list[MeasureConfig]:
    """Return the measures configured as subentries of the entry."""
    measures: list[MeasureConfig] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_MEASURE:
            continue
        data = subentry.data
        measures.append(
            MeasureConfig(
                measure_id=data[CONF_MEASURE_ID],
                subentry_id=subentry.subentry_id,
                name=subentry.title or data.get(CONF_NAME, data[CONF_MEASURE_ID]),
                date=date.fromisoformat(str(data[CONF_DATE])),
                category=data.get(CONF_CATEGORY, "other"),
                notes=data.get(CONF_NOTES, ""),
            )
        )
    return measures


def method_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return the methods/season options with defaults applied."""
    opts = dict(entry.options.get(OPT_METHODS, {}))
    opts.setdefault(CONF_SEASON_START, SEASON_START_OCTOBER)
    opts.setdefault(CONF_METHODS_ENABLED, list(DEFAULT_METHODS_ENABLED))
    opts.setdefault(CONF_METHODS_PRIMARY, DEFAULT_METHOD_PRIMARY)
    opts.setdefault(CONF_CLASSIC_WEIGHTED, True)
    opts.setdefault(CONF_CLASSIC_BASE_TEMP, DEFAULT_CLASSIC_BASE_TEMP)
    opts.setdefault(CONF_CLASSIC_HEATING_LIMIT, DEFAULT_CLASSIC_HEATING_LIMIT)
    opts.setdefault(CONF_PBL_PARAMETER_SET, "practical")
    opts.setdefault(CONF_PBL_WIND_MODE, "linear")
    opts.setdefault(CONF_PBL_INCLUDE_SUN, False)
    opts.setdefault(CONF_HOUSE_FIT_WIND, True)
    return opts


def advanced_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return the advanced options with defaults applied (flattened)."""
    opts = dict(entry.options.get(OPT_ADVANCED, {}))
    opts.setdefault(CONF_PBL_TST_WINTER, DEFAULT_PBL_TST["winter"])
    opts.setdefault(CONF_PBL_TST_SHOULDER, DEFAULT_PBL_TST["shoulder"])
    opts.setdefault(CONF_PBL_TST_TRANSITION, DEFAULT_PBL_TST["transition"])
    opts.setdefault(CONF_PBL_TST_SUMMER, DEFAULT_PBL_TST["summer"])
    opts.setdefault(CONF_PBL_RER_WINTER, DEFAULT_PBL_RER["winter"])
    opts.setdefault(CONF_PBL_RER_SHOULDER, DEFAULT_PBL_RER["shoulder"])
    opts.setdefault(CONF_PBL_RER_TRANSITION, DEFAULT_PBL_RER["transition"])
    opts.setdefault(CONF_PBL_RER_SUMMER, DEFAULT_PBL_RER["summer"])
    opts.setdefault(CONF_PBL_TOP, DEFAULT_PBL_TOP)
    opts.setdefault(CONF_PBL_WIND_SQRT_COEF, DEFAULT_PBL_WIND_SQRT_COEF)
    opts.setdefault(CONF_OUTLIER_THRESHOLD, DEFAULT_OUTLIER_THRESHOLD)
    opts.setdefault(CONF_MIN_FIT_DAYS, DEFAULT_MIN_FIT_DAYS)
    return opts


def history_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return the history options with defaults applied."""
    opts = dict(entry.options.get(OPT_HISTORY, {}))
    opts.setdefault(
        CONF_BACKFILL_YEARS, entry.data.get(CONF_BACKFILL_YEARS, DEFAULT_BACKFILL_YEARS)
    )
    opts.setdefault(
        CONF_CLIMATOLOGY_YEARS, entry.data.get(CONF_CLIMATOLOGY_YEARS, DEFAULT_CLIMATOLOGY_YEARS)
    )
    return opts


def summer_window(entry: ConfigEntry) -> tuple[str, str]:
    """Return the site-level summer window as two MM-DD strings."""
    dhw_opts = entry.options.get(OPT_DHW, {})
    return (
        _month_day_text(dhw_opts.get(CONF_SUMMER_START), DEFAULT_SUMMER_START),
        _month_day_text(dhw_opts.get(CONF_SUMMER_END), DEFAULT_SUMMER_END),
    )


def season_config(entry: ConfigEntry) -> Any:
    """Return the core SeasonConfig of the entry."""
    month, day = SEASON_START_DATES[method_options(entry)[CONF_SEASON_START]]
    return core_models.SeasonConfig(start_month=month, start_day=day)


def _season_window(season: Any) -> SeasonWindow:
    return SeasonWindow(label=str(season.label), start=season.start, end=season.end)


def season_for(entry: ConfigEntry, day: date) -> SeasonWindow:
    """Return the heating season (per the configured season start) containing ``day``."""
    return _season_window(core_season.season_for(day, season_config(entry)))


def season_from_label(entry: ConfigEntry, label: str) -> SeasonWindow:
    """Return the season window for a label such as ``2024/25``; raises ValueError."""
    text = label.strip()
    parts = text.split("/")
    if len(parts) == 2 and len(parts[1]) == 4:
        text = f"{parts[0]}/{parts[1][2:]}"
    return _season_window(core_season.season_window(text, season_config(entry)))


def weather_signature_from_data(data: Mapping[str, Any]) -> str:
    """Return a string identifying the weather source of site data.

    A change of this signature triggers a fresh weather history and a full recompute.
    """
    weather = data.get(CONF_WEATHER, {})
    ha_entities = weather.get(CONF_HA_ENTITIES, {})
    return "|".join(
        str(part)
        for part in (
            weather.get(CONF_PROVIDER),
            weather.get(CONF_STATION_ID),
            ha_entities.get(CONF_TEMPERATURE_ENTITY),
            ha_entities.get(CONF_WIND_ENTITY),
            ha_entities.get(CONF_RADIATION_ENTITY),
            round(float(data.get(CONF_LATITUDE, 0.0)), 3),
            round(float(data.get(CONF_LONGITUDE, 0.0)), 3),
        )
    )


def weather_signature(entry: ConfigEntry) -> str:
    """Return the weather source signature of a config entry."""
    return weather_signature_from_data(entry.data)


# --------------------------------------------------------------------------------
# Site model
# --------------------------------------------------------------------------------


def _core_generator(config: GeneratorConfig, summer: tuple[str, str]) -> Any:
    """Build a core Generator from a GeneratorConfig."""
    carrier = core_models.CarrierInput(
        energy_entity=config.energy_entity,
        unit=core_models.CarrierUnit(config.unit),
        thermal_entity=config.thermal_entity,
        dhw_entity=config.dhw_entity,
        electric_entity=config.electric_entity,
    )
    conversion = core_models.Conversion(
        mode=core_models.ConversionMode(config.conversion_mode),
        efficiency=config.efficiency,
        heating_value=config.heating_value_kwh_per_m3,
        scop=config.scop,
        cop=config.cop,
        factor=config.factor,
    )
    dhw = core_models.DhwConfig(
        mode=core_models.DhwMode(config.dhw_mode),
        fixed_per_day=config.dhw_fixed_per_day,
        summer_start=summer[0],
        summer_end=summer[1],
    )
    return core_models.Generator(
        id=config.generator_id,
        name=config.name,
        kind=core_models.GeneratorKind(config.kind),
        role=core_models.Role(config.role),
        carrier=carrier,
        conversion=conversion,
        dhw=dhw,
        price_entity=config.price_entity,
        co2_factor=config.co2_factor,
    )


def _pbl_custom_table(advanced: dict[str, Any]) -> tuple[tuple[float, float, float], ...] | None:
    """Return the advanced PBL month table, or ``None`` when every value is still the default."""
    groups = (
        (CONF_PBL_TST_WINTER, CONF_PBL_RER_WINTER, "winter"),
        (CONF_PBL_TST_SHOULDER, CONF_PBL_RER_SHOULDER, "shoulder"),
        (CONF_PBL_TST_TRANSITION, CONF_PBL_RER_TRANSITION, "transition"),
        (CONF_PBL_TST_SUMMER, CONF_PBL_RER_SUMMER, "summer"),
    )
    top = float(advanced[CONF_PBL_TOP])
    table = tuple(
        (float(advanced[tst_key]), float(advanced[rer_key]), top) for tst_key, rer_key, _ in groups
    )
    defaults = tuple(
        (DEFAULT_PBL_TST[name], DEFAULT_PBL_RER[name], DEFAULT_PBL_TOP) for _, _, name in groups
    )
    if all(
        abs(a - b) < 1e-9
        for row, drow in zip(table, defaults, strict=True)
        for a, b in zip(row, drow, strict=True)
    ):
        return None
    return table


def build_site_from_entry(entry: ConfigEntry) -> Any:
    """Build the core ``Site`` model from the config entry, options and subentries."""
    data = entry.data
    methods = method_options(entry)
    advanced = advanced_options(entry)
    history = history_options(entry)
    weather = data.get(CONF_WEATHER, {})
    ha_entities = weather.get(CONF_HA_ENTITIES, {})
    summer = summer_window(entry)

    weather_config = core_models.WeatherSourceConfig(
        provider=core_models.Provider(weather.get(CONF_PROVIDER, PROVIDER_OPEN_METEO)),
        station_id=weather.get(CONF_STATION_ID),
        fallback=core_models.Provider(weather.get(CONF_FALLBACK) or FALLBACK_NONE),
        ha_entities={
            key: value
            for key, value in (
                ("temperature", ha_entities.get(CONF_TEMPERATURE_ENTITY)),
                ("wind", ha_entities.get(CONF_WIND_ENTITY)),
                ("radiation", ha_entities.get(CONF_RADIATION_ENTITY)),
            )
            if value
        },
    )
    # Advanced PBL month parameters: only passed as a custom table when the user changed
    # at least one value, so the built-in "practical"/"optimal" sets keep working.
    custom_table = _pbl_custom_table(advanced)
    method_config = core_models.MethodConfig(
        enabled=list(methods[CONF_METHODS_ENABLED]),
        primary=methods[CONF_METHODS_PRIMARY],
        classic=core_models.ClassicParams(
            base_temp=float(methods[CONF_CLASSIC_BASE_TEMP]),
            heating_limit=float(methods[CONF_CLASSIC_HEATING_LIMIT]),
            weighted=bool(methods[CONF_CLASSIC_WEIGHTED]),
        ),
        pbl=core_models.PblParams(
            parameter_set=methods[CONF_PBL_PARAMETER_SET],
            wind_mode=methods[CONF_PBL_WIND_MODE],
            include_sun=bool(methods[CONF_PBL_INCLUDE_SUN]),
            include_top=False,
            wind_sqrt_coef=float(advanced[CONF_PBL_WIND_SQRT_COEF]),
            custom_table=custom_table,
        ),
        house=core_models.HouseParams(fit_wind=bool(methods[CONF_HOUSE_FIT_WIND])),
    )
    generators = [_core_generator(config, summer) for config in generator_configs(entry)]
    rooms = [
        core_models.Room(
            id=room.room_id,
            name=room.name,
            area_id=room.area_id,
            demand_entity=room.demand_entity,
            demand_kind=core_models.DemandKind(room.demand_kind),
            temperature_entity=room.temperature_entity,
            emitter_kind=core_models.EmitterKind(room.emitter_kind),
            rated_output_w=room.rated_output_w,
            floor_area_m2=room.floor_area_m2,
            volume_m3=room.volume_m3,
            price_entity=room.price_entity,
            enabled=room.enabled,
        )
        for room in room_configs(entry)
    ]
    measures = [
        core_models.Measure(
            id=measure.measure_id,
            name=measure.name,
            date=measure.date,
            category=core_models.MeasureCategory(measure.category),
            notes=measure.notes,
        )
        for measure in measure_configs(entry)
    ]
    return core_models.Site(
        id=data[CONF_SITE_ID],
        name=data[CONF_NAME],
        latitude=float(data[CONF_LATITUDE]),
        longitude=float(data[CONF_LONGITUDE]),
        timezone=data[CONF_TIMEZONE],
        country=data.get(CONF_COUNTRY, ""),
        season=season_config(entry),
        methods=method_config,
        backfill_years=int(history[CONF_BACKFILL_YEARS]),
        climatology_years=int(history[CONF_CLIMATOLOGY_YEARS]),
        weather=weather_config,
        generators=generators,
        measures=measures,
        rooms=rooms,
    )


# --------------------------------------------------------------------------------
# Weather providers
# --------------------------------------------------------------------------------


def _weather_day_from_core(item: Any) -> WeatherDay:
    """Convert a core DailyWeather into the shell's WeatherDay."""
    return WeatherDay(
        date=item.date,
        t_mean=item.t_mean,
        wind_mean=item.wind_mean,
        radiation=item.radiation,
        t_min=item.t_min,
        t_max=item.t_max,
        provisional=bool(item.provisional),
        source=str(item.source or ""),
    )


def to_core_weather(days: Iterable[WeatherDay]) -> dict[date, Any]:
    """Convert shell WeatherDay objects into core DailyWeather objects keyed by date."""
    result: dict[date, Any] = {}
    for day in days:
        if day.t_mean is None:
            continue
        result[day.date] = core_models.DailyWeather(
            date=day.date,
            t_mean=float(day.t_mean),
            wind_mean=day.wind_mean,
            radiation=day.radiation,
            t_min=day.t_min,
            t_max=day.t_max,
            provisional=day.provisional,
            source=day.source,
        )
    return result


def _provider(
    session: ClientSession,
    provider: str,
    station_id: str | None,
    latitude: float,
    longitude: float,
    timezone: str,
) -> Any:
    """Instantiate a core weather provider bound to the HA aiohttp session."""
    if provider == PROVIDER_KNMI:
        return core_knmi.KnmiProvider(session=session, station_id=str(station_id))
    if provider == PROVIDER_OPEN_METEO:
        return core_open_meteo.OpenMeteoProvider(
            session=session, latitude=latitude, longitude=longitude, timezone=timezone
        )
    raise CoreError(f"Provider {provider} has no network fetcher")


async def _fetch(provider: Any, start: date, end: date) -> list[WeatherDay]:
    """Fetch daily weather from a core provider and map errors."""
    try:
        result = await provider.fetch_daily(start, end)
    except (ClientError, TimeoutError, OSError) as err:
        raise WeatherCannotConnect(str(err)) from err
    except CoreError:
        raise
    except Exception as err:  # noqa: BLE001 - the providers raise plain aiohttp/parse errors
        raise WeatherCannotConnect(str(err)) from err
    days = [_weather_day_from_core(item) for item in result]
    if not days:
        raise WeatherNoData("no rows returned")
    return days


async def async_test_weather(
    session: ClientSession,
    weather: Mapping[str, Any],
    latitude: float,
    longitude: float,
    timezone: str = "UTC",
) -> None:
    """Fetch the last 7 days from the configured provider to validate the configuration."""
    provider_name = weather.get(CONF_PROVIDER)
    if provider_name == PROVIDER_HA_SENSORS:
        return
    end = date.today()
    start = end - timedelta(days=7)
    provider = _provider(
        session, provider_name, weather.get(CONF_STATION_ID), latitude, longitude, timezone
    )
    days = await _fetch(provider, start, end)
    if all(day.t_mean is None for day in days):
        raise WeatherNoData("no temperature values")


async def async_fetch_weather(
    session: ClientSession,
    weather: Mapping[str, Any],
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    timezone: str = "UTC",
) -> list[WeatherDay]:
    """Fetch daily weather for a date range, falling back to the fallback provider."""
    provider_name = weather.get(CONF_PROVIDER)
    fallback_name = weather.get(CONF_FALLBACK, FALLBACK_NONE)
    provider = _provider(
        session, provider_name, weather.get(CONF_STATION_ID), latitude, longitude, timezone
    )
    try:
        days = await _fetch(provider, start, end)
    except CoreError:
        if fallback_name in (FALLBACK_NONE, None, provider_name, PROVIDER_HA_SENSORS):
            raise
        provider_name = fallback_name
        fallback = _provider(session, fallback_name, None, latitude, longitude, timezone)
        days = await _fetch(fallback, start, end)
    if provider_name == PROVIDER_KNMI:
        # The KNMI parser marks the last requested day provisional; for a historic
        # window (backfill chunk) that day is definitive. Only the last two days
        # before today can still change (METHODS 2).
        cutoff = date.today() - timedelta(days=2)
        for day in days:
            if day.provisional and day.date < cutoff:
                day.provisional = False
    return days


def weather_from_ha_sensors(
    weather: Mapping[str, Any],
    means: Mapping[str, Mapping[date, float]],
    start: date,
    end: date,
) -> list[WeatherDay]:
    """Build weather days from daily means of Home Assistant sensors (METHODS 2)."""
    entities = weather.get(CONF_HA_ENTITIES, {})
    temperature = means.get(entities.get(CONF_TEMPERATURE_ENTITY, ""), {})
    wind = means.get(entities.get(CONF_WIND_ENTITY, ""), {})
    radiation = means.get(entities.get(CONF_RADIATION_ENTITY, ""), {})
    days: list[WeatherDay] = []
    day = start
    while day <= end:
        t_mean = temperature.get(day)
        if t_mean is not None:
            mean_radiation = radiation.get(day)
            days.append(
                WeatherDay(
                    date=day,
                    t_mean=t_mean,
                    wind_mean=wind.get(day),
                    # Mean W/m2 over a day -> J/cm2 per day: W/m2 * 24 h * 0.36
                    radiation=mean_radiation * 24 * 0.36 if mean_radiation is not None else None,
                    provisional=day == end,
                    source=f"ha:{entities.get(CONF_TEMPERATURE_ENTITY)}",
                )
            )
        day += timedelta(days=1)
    return days


# --------------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------------


def _energy_series(
    energy: Mapping[str, Mapping[date, DailyEnergyInput]], attribute: str
) -> dict[str, dict[date, Any]]:
    """Return per-generator ``{day: (amount, flags)}`` series for one input attribute."""
    imported_flag = core_flags.Flag.IMPORTED
    series: dict[str, dict[date, Any]] = {}
    for generator_id, days in energy.items():
        rows: dict[date, Any] = {}
        for day, item in days.items():
            value = getattr(item, attribute)
            if value is None:
                continue
            flags = {imported_flag} if item.imported and attribute == "carrier" else set()
            rows[day] = (float(value), flags)
        if rows:
            series[generator_id] = rows
    return series


def fit_from_dict(fit: Mapping[str, Any] | None) -> Any:
    """Rebuild a core SignatureFit from its stored dict (None passes through)."""
    if not fit:
        return None
    return core_models.SignatureFit.from_dict(fit)


def climatology_from_dict(climatology: Mapping[str, Any] | None) -> Any:
    """Rebuild a core Climatology from its stored dict (None passes through)."""
    if not climatology:
        return None
    return core_models.Climatology.from_dict(climatology)


def build_daily_records(
    site: Any,
    weather: Iterable[WeatherDay],
    energy: Mapping[str, Mapping[date, DailyEnergyInput]],
    baselines: Mapping[str, float],
    house_fit: Mapping[str, Any] | None,
    start: date,
    end: date,
    co2_factors: Mapping[str, float] | None = None,
) -> list[Any]:
    """Run the core pipeline and return core DailyRecord objects for start..end."""
    fit = fit_from_dict(house_fit)
    outliers = [date.fromisoformat(str(day)) for day in (house_fit or {}).get("outliers", [])]
    # Price entities are not read from the recorder yet (v1.0 / F18); cost_eur stays
    # None here. CO2 still uses the configured per-generator factor.
    # The baselines are always passed (possibly empty): with None the core would
    # estimate them from this window alone, which for a 90-day winter chunk yields a
    # bogus "summer" baseline. Without a baseline all heat counts as space heating.
    return core_pipeline.build_daily_records(
        site,
        to_core_weather(weather),
        _energy_series(energy, "carrier"),
        thermal_by_generator=_energy_series(energy, "thermal"),
        electric_by_generator=_energy_series(energy, "electric"),
        dhw_by_generator=_energy_series(energy, "dhw"),
        baselines=dict(baselines),
        house_fit=fit,
        co2_factors=dict(co2_factors) if co2_factors else None,
        outlier_dates=outliers,
        start=start,
        end=end,
    )


def estimate_baselines(
    site: Any, energy: Mapping[str, Mapping[date, DailyEnergyInput]]
) -> dict[str, float]:
    """Return the DHW baseline per generator (METHODS 6) from a long energy series.

    Only generators that split their heat with a baseline (role ``both`` and DHW mode
    ``baseline`` or ``measured``, the latter falls back to the baseline on days
    without a measurement) get one; a space-only generator has no DHW share.
    """
    result = core_pipeline.estimate_baselines(
        site, _energy_series(energy, "carrier"), _energy_series(energy, "thermal")
    )
    wanted = {generator.id for generator in site.generators if _uses_baseline(generator)}
    return {
        generator_id: float(value)
        for generator_id, value in result.items()
        if value is not None and generator_id in wanted
    }


def _uses_baseline(generator: Any) -> bool:
    """Return True when the DHW split of a core generator can use a baseline."""
    return generator.role is core_models.Role.BOTH and generator.dhw.mode in (
        core_models.DhwMode.BASELINE,
        core_models.DhwMode.MEASURED,
    )


def baselines_in_kwh(site: Any, baselines: Mapping[str, float]) -> dict[str, float]:
    """Convert DHW baselines from carrier units to kWh of heat per day (sensor value).

    A heat pump baseline estimated from a thermal-only series is already in kWh.
    """
    result: dict[str, float] = {}
    for generator in site.generators:
        value = baselines.get(generator.id)
        if value is None or not _uses_baseline(generator):
            continue
        if generator.carrier.energy_entity is None and generator.carrier.thermal_entity:
            result[generator.id] = float(value)
        else:
            result[generator.id] = float(value) * core_heat.static_heat_per_unit(generator)
    return result


def _flag_names(flags: Iterable[Any]) -> list[str]:
    """Return upper-case flag names (``Flag.WEATHER_MISSING`` -> ``WEATHER_MISSING``)."""
    names = {str(getattr(flag, "name", flag)).upper() for flag in flags or ()}
    return sorted(names)


def record_flags(record: Any) -> list[str]:
    """Return the flag names of a core DailyRecord."""
    return _flag_names(getattr(record, "flags", ()))


def record_is_usable(record: Any) -> bool:
    """Return True when the record carries no exclusion flag."""
    return core_flags.is_usable(getattr(record, "flags", ()))


def record_to_metrics(record: Any, generators: Iterable[GeneratorConfig]) -> DayMetrics:
    """Project a core DailyRecord onto the statistics metrics (DATA_MODEL 2.2)."""
    dd: Mapping[str, float] = record.dd or {}
    flags = record_flags(record)
    has_energy = FLAG_ENERGY_MISSING not in flags
    values: dict[str, float | None] = {
        METRIC_T_MEAN: record.t_mean,
        METRIC_TAC_PBL: record.tac_pbl,
        METRIC_TAC_HOUSE: record.tac_house,
        METRIC_DD_CLASSIC: dd.get(METHOD_CLASSIC),
        METRIC_DD_KNMI14: dd.get(METHOD_KNMI14),
        METRIC_DD_PBL: dd.get(METHOD_PBL),
        METRIC_DD_HOUSE: dd.get(METHOD_HOUSE),
        METRIC_HEAT_SPACE: record.heat_space_kwh if has_energy else None,
        METRIC_HEAT_DHW: record.heat_dhw_kwh if has_energy else None,
    }
    by_generator: Mapping[str, Any] = record.heat_by_generator or {}
    gas_m3 = 0.0
    has_gas = False
    electric_hp = 0.0
    has_hp = False
    cop: float | None = None
    for generator in generators:
        energy = by_generator.get(generator.generator_id)
        if energy is None:
            continue
        values[generator_metric(generator.generator_id)] = energy.heat_space_kwh
        if generator.role in (ROLE_BOTH, ROLE_DHW):
            values[generator_dhw_metric(generator.generator_id)] = energy.heat_dhw_kwh
        if generator.kind == KIND_GAS_BOILER and energy.carrier_amount is not None:
            has_gas = True
            gas_m3 += float(energy.carrier_amount)
        if generator.is_heat_pump:
            has_hp = True
            electric_hp += float(energy.electric_kwh or 0.0)
            if energy.cop_day is not None:
                cop = float(energy.cop_day)
    if has_gas:
        values[METRIC_GAS] = gas_m3
    if has_hp:
        values[METRIC_ELECTRIC_HP] = electric_hp
    tac_primary = record.tac_house if record.tac_house is not None else record.tac_pbl
    return DayMetrics(
        date=record.date,
        values=values,
        flags=flags,
        provisional=FLAG_WEATHER_PROVISIONAL in flags,
        cop=cop,
        tac_primary=tac_primary,
    )


# --------------------------------------------------------------------------------
# Rooms (METHODS 12)
# --------------------------------------------------------------------------------


def _demand_statistic_value(kind: str, integral: float | None) -> float | None:
    """Value written to ``room_<id>_demand`` (percent, hours, or kWh)."""
    if integral is None:
        return None
    if kind in ("percentage", "valve_position"):
        return float(integral) * 100.0
    if kind == "binary":
        return float(integral) * 24.0
    return float(integral)


def allocate_rooms(
    site: Any,
    records: Iterable[Any],
    inputs_by_day: Mapping[date, Mapping[str, Any]],
    output_w_per_m2: Mapping[str, float] | None = None,
) -> tuple[list[Any], dict[date, float]]:
    """Allocate site space heat across rooms; returns room records and unallocated kWh."""
    day_inputs: dict[date, dict[str, Any]] = {}
    for day, rooms in inputs_by_day.items():
        converted: dict[str, Any] = {}
        for room_id, item in rooms.items():
            if isinstance(item, core_rooms.RoomDayInput):
                converted[room_id] = item
            else:
                converted[room_id] = core_rooms.RoomDayInput(
                    raw=item.get("raw"),
                    t_room_mean=item.get("t_room_mean"),
                    from_history=bool(item.get("from_history", False)),
                    heating_hours=item.get("heating_hours"),
                )
        day_inputs[day] = converted
    return core_rooms.allocate_period(
        site.enabled_rooms,
        day_inputs,
        records,
        output_w_per_m2=output_w_per_m2,
    )


def merge_room_metrics(
    metrics: list[DayMetrics],
    room_records: Iterable[Any],
    unallocated: Mapping[date, float],
    rooms: Iterable[RoomConfig],
) -> list[DayMetrics]:
    """Attach room and unallocated values onto existing day metrics."""
    by_date: dict[date, list[Any]] = {}
    for record in room_records:
        by_date.setdefault(record.date, []).append(record)
    rooms_by_id = {room.room_id: room for room in rooms}
    for day in metrics:
        day.values[METRIC_HEAT_UNALLOCATED] = unallocated.get(day.date, 0.0)
        for record in by_date.get(day.date, ()):
            room = rooms_by_id.get(record.room_id)
            kind = room.demand_kind if room is not None else "percentage"
            day.values[room_heat_metric(record.room_id)] = record.heat_room_kwh
            day.values[room_demand_metric(record.room_id)] = _demand_statistic_value(
                kind, record.demand_integral
            )
            if record.t_room_mean is not None:
                day.values[room_t_mean_metric(record.room_id)] = record.t_room_mean
    return metrics


def apply_room_not_fitted(
    room_records: Iterable[Any],
    site_records: Iterable[Any],
    *,
    min_days: int = DEFAULT_MIN_FIT_DAYS,
    skip_room_ids: Iterable[str] = (),
) -> set[str]:
    """Add ROOM_NOT_FITTED on rooms with fewer than ``min_days`` usable fit days."""
    return core_room_signature.apply_room_not_fitted(
        room_records,
        site_records,
        min_days=min_days,
        skip_room_ids=skip_room_ids,
    )


def fit_room_signature(
    room: Any,
    room_records: Iterable[Any],
    site_records: Iterable[Any],
    *,
    start: date,
    end: date,
    min_days: int = DEFAULT_MIN_FIT_DAYS,
    outlier_k: float = DEFAULT_OUTLIER_THRESHOLD,
) -> dict[str, Any] | None:
    """Fit one room's energy signature; returns a JSON-friendly dict or None."""
    fit = core_room_signature.fit_room_signature(
        room,
        room_records,
        site_records,
        core_models.Period(start=start, end=end),
        min_days=min_days,
        outlier_k=outlier_k,
    )
    if fit is None:
        return None
    return _flatten_fit(fit)


# --------------------------------------------------------------------------------
# Analyses (fits, comparisons, forecast, climatology)
# --------------------------------------------------------------------------------


def _to_plain(value: Any) -> Any:
    """Convert a core result (JsonMixin dataclass or mapping) into JSON-friendly data."""
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_plain(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _flatten_fit(fit: Any) -> dict[str, Any]:
    """Return a fit dict with flat period keys used by the store and the sensors."""
    plain = _to_plain(fit)
    period = plain.get("period") or {}
    plain["period_start"] = period.get("start")
    plain["period_end"] = period.get("end")
    return plain


def fit_signature(
    site: Any,
    records: Iterable[Any],
    *,
    start: date,
    end: date,
    tac_preset: str = "house",
    fit_wind: bool = True,
    min_days: int = DEFAULT_MIN_FIT_DAYS,
    outlier_k: float = DEFAULT_OUTLIER_THRESHOLD,
) -> dict[str, Any] | None:
    """Fit the energy signature (METHODS 7); returns a JSON-friendly dict or None."""
    fit = core_signature.fit_signature(
        records,
        core_models.Period(start=start, end=end),
        tac_key=TAC_KEY_FOR_PRESET.get(tac_preset, "tac_house"),
        fit_wind=fit_wind,
        min_days=min_days,
        outlier_k=outlier_k,
        site_id=site.id,
    )
    if fit is None:
        return None
    return _flatten_fit(fit)


def compare_periods(
    site: Any,
    records: Iterable[Any],
    *,
    base: tuple[date, date],
    target: tuple[date, date],
    method: str,
    climatology: Mapping[str, Any] | None,
    fit_wind: bool = True,
    min_days: int = DEFAULT_MIN_FIT_DAYS,
) -> dict[str, Any]:
    """Compare two periods (METHODS 8.2-8.3) and return a Comparison as a dict.

    ``method`` is a degree-day method for the k-value comparison, or ``signature``
    for the normalised (NAC) comparison of two fits with a bootstrap interval.
    """
    records = list(records)
    base_period = core_models.Period(start=base[0], end=base[1], label="base")
    target_period = core_models.Period(start=target[0], end=target[1], label="target")
    dd_method = METHOD_HOUSE if method == "signature" else method
    try:
        comparison = core_compare.compare_periods(
            records, base_period, target_period, dd_method, min_days
        )
    except core_compare.InsufficientDataError as err:
        raise InsufficientData(str(err)) from err
    plain = _to_plain(comparison)
    if method != "signature":
        return plain
    clim = climatology_from_dict(climatology)
    fit_before = core_signature.fit_signature(
        records, base_period, fit_wind=fit_wind, min_days=min_days, site_id=site.id
    )
    fit_after = core_signature.fit_signature(
        records, target_period, fit_wind=fit_wind, min_days=min_days, site_id=site.id
    )
    plain["method"] = "signature"
    plain["fit_base"] = _flatten_fit(fit_before) if fit_before else None
    plain["fit_target"] = _flatten_fit(fit_after) if fit_after else None
    if clim is None or fit_before is None or fit_after is None:
        plain["note"] = "NAC saving needs a climatology and a fit of both periods"
        return plain
    saving, interval = core_normalize.saving_between(
        fit_before, fit_after, clim, records, records, season_window=base_period
    )
    plain["nac_base"] = core_normalize.normalized_consumption(fit_before, clim, base_period)
    plain["nac_target"] = core_normalize.normalized_consumption(fit_after, clim, base_period)
    plain["saving_pct"] = saving
    plain["ci95_saving"] = list(interval) if interval else None
    return plain


def measure_effect(
    site: Any,
    records: Iterable[Any],
    *,
    measure_date: date,
    climatology: Mapping[str, Any] | None,
    method: str = METHOD_CLASSIC,
    fit_wind: bool = True,
    min_days: int = DEFAULT_MIN_FIT_DAYS,
) -> dict[str, Any]:
    """Effect of a measure (METHODS 8.4): fits before/after with NAC saving plus k-values."""
    try:
        comparison, fit_before, fit_after = core_compare.measure_effect(
            records,
            measure_date,
            site.season,
            climatology_from_dict(climatology),
            method=method,
            fit_wind=fit_wind,
            min_days=min_days,
        )
    except core_compare.InsufficientDataError as err:
        raise InsufficientData(str(err)) from err
    plain = _to_plain(comparison)
    plain["fit_before"] = _flatten_fit(fit_before) if fit_before else None
    plain["fit_after"] = _flatten_fit(fit_after) if fit_after else None
    return plain


def forecast_season(
    site: Any,
    records: Iterable[Any],
    *,
    season: SeasonWindow,
    climatology: Mapping[str, Any] | None,
    method: str,
    dhw_per_day: float,
    fit: Mapping[str, Any] | None,
    today: date,
    generators: Iterable[GeneratorConfig],
) -> dict[str, Any]:
    """Forecast the running season (METHODS 8.5) and return it as a flat dict."""
    if not climatology:
        raise InsufficientData("no climatology available yet")
    core_fit = fit_from_dict(fit)
    clim_data = dict(climatology)
    if method == METHOD_HOUSE and core_fit is not None:
        # The stored house degree-day climatology was built with the balance
        # temperature known at that time (or the 15.5 fallback before the first
        # fit). When it differs from the fit, k_ytd (fitted T_b) and DD_rest would
        # disagree; drop the stale series so the core derives DD_rest from the TAC
        # climatology with the fitted balance temperature (see build_climatology).
        built_with = clim_data.get(CLIMATOLOGY_BALANCE_KEY)
        if built_with is None or abs(float(built_with) - core_fit.balance_temp) > 1e-6:
            dd_by_doy = dict(clim_data.get("dd_by_doy") or {})
            dd_by_doy.pop(METHOD_HOUSE, None)
            clim_data["dd_by_doy"] = dd_by_doy
    clim = climatology_from_dict(clim_data)
    forecast = core_forecast.forecast_season(
        records,
        core_models.Season(label=season.label, start=season.start, end=season.end),
        clim,
        method=method,
        dhw_per_day=dhw_per_day,
        fit=core_fit,
        today=today,
    )
    plain = _to_plain(forecast)
    plain["season"] = season.label
    generator_list = list(generators)
    carriers = core_forecast.forecast_carrier_amounts(forecast, site)
    gas_m3 = 0.0
    electric_kwh = 0.0
    has_gas = False
    has_electric = False
    for generator in generator_list:
        amount = carriers.get(generator.generator_id)
        if generator.kind == KIND_GAS_BOILER:
            has_gas = True
            gas_m3 += amount or 0.0
        elif generator.is_heat_pump or generator.kind == KIND_ELECTRIC_HEATER:
            has_electric = True
            electric_kwh += amount or 0.0
    plain["per_carrier"] = carriers
    plain["gas_m3_forecast"] = gas_m3 if has_gas else None
    plain["electric_kwh_forecast"] = electric_kwh if has_electric else None
    return plain


def build_climatology(
    site: Any, weather: Iterable[WeatherDay], years: int, house_balance_temp: float | None = None
) -> dict[str, Any]:
    """Build the climatology (METHODS 8.1) from multi-year weather and return it as a dict.

    The balance temperature used for the ``house`` degree-day series is stored under
    ``CLIMATOLOGY_BALANCE_KEY`` (None before the first fit) so that ``forecast_season``
    can detect a stale series; the core ignores the extra key.
    """
    climatology = core_climatology.build_climatology(
        to_core_weather(weather).values(),
        years,
        site_id=site.id,
        method_config=site.methods,
        house_balance_temp=house_balance_temp,
    )
    plain = _to_plain(climatology)
    plain[CLIMATOLOGY_BALANCE_KEY] = house_balance_temp
    return plain


def parse_readings_csv(text: str, mapping: Mapping[str, Any]) -> list[tuple[datetime, float]]:
    """Parse a CSV export of meter readings (mindergas or generic) into (datetime, reading)."""
    return core_csv.parse_readings_csv(
        text,
        date_col=mapping.get("date_column", "datum"),
        value_col=mapping.get("reading_column", "stand"),
        date_format=mapping.get("date_format", "%d-%m-%Y"),
        delimiter=mapping.get("delimiter", ";"),
        decimal=mapping.get("decimal", ","),
    )


def inspect_readings_csv(
    text: str,
    *,
    date_col: str | None = None,
    value_col: str | None = None,
    date_format: str | None = None,
    delimiter: str | None = None,
    decimal: str | None = None,
) -> core_csv.CsvInspection:
    """Auto-detect CSV columns and parse readings for the import wizard."""
    return core_csv.inspect_readings_csv(
        text,
        date_col=date_col,
        value_col=value_col,
        date_format=date_format,
        delimiter=delimiter,
        decimal=decimal,
    )


def daily_consumption_from_readings(
    readings: Iterable[tuple[datetime, float]], tz: tzinfo
) -> tuple[dict[date, float], dict[date, list[str]]]:
    """Convert meter readings to consumption per local day (METHODS 9)."""
    daily = core_readings.readings_to_daily(list(readings), tz)
    consumption: dict[date, float] = {}
    flags: dict[date, list[str]] = {}
    for day, (amount, day_flags) in daily.items():
        consumption[day] = float(amount)
        names = _flag_names(day_flags)
        if names:
            flags[day] = names
    return consumption, flags


def record_day_summary(record: Any) -> dict[str, Any]:
    """Return a compact JSON summary of a record (diagnostics)."""
    return {
        "date": record.date.isoformat(),
        "t_mean": record.t_mean,
        "tac_pbl": record.tac_pbl,
        "tac_house": record.tac_house,
        "dd": dict(record.dd or {}),
        "heat_space_kwh": record.heat_space_kwh,
        "heat_dhw_kwh": record.heat_dhw_kwh,
        "flags": record_flags(record),
    }
