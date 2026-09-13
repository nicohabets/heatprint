"""Data model of the calculation core (DATA_MODEL).

Three layers:

1. Configuration - what the user sets up (site, weather source, generators, methods,
   measures). Frozen dataclasses with the defaults of DATA_MODEL section 1.
2. Facts - daily weather, daily energy per generator, daily records, climatology.
3. Derived - signature fits, comparisons, forecasts.

All models provide ``to_dict()`` / ``from_dict()`` producing plain JSON-able dicts
(enums as values, dates as ISO strings, sets as sorted lists) because the Home
Assistant layer stores them in a JSON store.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, StrEnum
from typing import Any, TypeVar

from .constants import (
    ELEC_CO2_KG_PER_KWH,
    GAS_CO2_KG_PER_M3,
    GAS_HS_KWH_PER_M3,
    HOUSE_FALLBACK_BALANCE_TEMP,
    PBL_TAC_WEIGHTS,
    PBL_WIND_SQRT_COEF,
)
from .flags import Flag, is_usable

T = TypeVar("T", bound="JsonMixin")


# --- Enums --------------------------------------------------------------------------------------


class Provider(StrEnum):
    """Weather provider (DATA_MODEL section 1.2)."""

    KNMI = "knmi"
    OPEN_METEO = "open_meteo"
    HA_SENSORS = "ha_sensors"
    NONE = "none"


class GeneratorKind(StrEnum):
    """Kind of heat generator (METHODS section 5)."""

    GAS_BOILER = "gas_boiler"
    HEAT_PUMP = "heat_pump"
    ELECTRIC_HEATER = "electric_heater"
    AIR_TO_AIR = "air_to_air"
    DISTRICT_HEAT = "district_heat"
    OTHER = "other"


class Role(StrEnum):
    """What a generator produces: space heating, domestic hot water, or both."""

    SPACE = "space"
    DHW = "dhw"
    BOTH = "both"


class CarrierUnit(StrEnum):
    """Unit of the cumulative energy counter of a generator."""

    M3 = "m3"
    KWH = "kwh"
    GJ = "gj"


class ConversionMode(StrEnum):
    """How the carrier amount is converted to heat (DATA_MODEL section 1.3)."""

    FIXED_EFFICIENCY = "fixed_efficiency"
    MEASURED_THERMAL = "measured_thermal"
    COP_FIXED = "cop_fixed"
    COP_CURVE = "cop_curve"
    FACTOR = "factor"


class DhwMode(StrEnum):
    """Domestic hot water split mode (METHODS section 6)."""

    MEASURED = "measured"
    BASELINE = "baseline"
    FIXED = "fixed"
    NONE = "none"


class MeasureCategory(StrEnum):
    """Category of an energy-saving measure (DATA_MODEL section 1.4)."""

    INSULATION = "insulation"
    INSTALLATION = "installation"
    BEHAVIOUR = "behaviour"
    OTHER = "other"


#: Names of the degree-day methods (METHODS section 4), in reporting order.
METHOD_NAMES: tuple[str, ...] = ("classic", "knmi14", "pbl", "house")


# --- JSON helpers -------------------------------------------------------------------------------


def _to_jsonable(value: Any) -> Any:
    """Recursively convert a model value into plain JSON-able Python objects."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {_key_to_json(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        return sorted(_to_jsonable(v) for v in value)
    if isinstance(value, list | tuple):
        return [_to_jsonable(v) for v in value]
    return value


def _key_to_json(key: Any) -> str:
    if isinstance(key, Enum):
        return str(key.value)
    if isinstance(key, date):
        return key.isoformat()
    return str(key)


def _from_jsonable(tp: Any, value: Any) -> Any:
    """Recursively convert plain JSON data into the annotated type ``tp``."""
    if value is None:
        return None
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin is types.UnionType or origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        # Try each member type; the first one that converts wins.
        for candidate in non_none:
            try:
                return _from_jsonable(candidate, value)
            except (TypeError, ValueError, KeyError):
                continue
        raise ValueError(f"cannot convert {value!r} to {tp}")
    if origin is list:
        (item_tp,) = args or (Any,)
        return [_from_jsonable(item_tp, v) for v in value]
    if origin in (set, frozenset):
        (item_tp,) = args or (Any,)
        return origin(_from_jsonable(item_tp, v) for v in value)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_from_jsonable(args[0], v) for v in value)
        if args:
            return tuple(_from_jsonable(a, v) for a, v in zip(args, value, strict=True))
        return tuple(value)
    if origin in (dict, Mapping):
        key_tp, val_tp = args or (Any, Any)
        return {_from_jsonable(key_tp, k): _from_jsonable(val_tp, v) for k, v in value.items()}
    if tp is Any:
        return value
    if isinstance(tp, type):
        if issubclass(tp, Enum):
            return tp(value)
        if tp is datetime:
            return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if tp is date:
            if isinstance(value, datetime):
                return value.date()
            return value if isinstance(value, date) else date.fromisoformat(str(value))
        if dataclasses.is_dataclass(tp):
            if isinstance(value, tp):
                return value
            return _dataclass_from_dict(tp, value)
        if tp is float:
            return float(value)
        if tp is int:
            if isinstance(value, bool):
                raise TypeError("bool is not int")
            return int(value)
        if tp is bool:
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "on")
            return bool(value)
        if tp is str:
            return str(value)
    return value


def _dataclass_from_dict(cls: type, data: Mapping[str, Any]) -> Any:
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        kwargs[f.name] = _from_jsonable(hints.get(f.name, Any), data[f.name])
    return cls(**kwargs)


class JsonMixin:
    """Adds ``to_dict`` / ``from_dict`` to a dataclass."""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain JSON-able dict of this model."""
        return _to_jsonable(self)

    @classmethod
    def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
        """Build the model from a dict produced by :meth:`to_dict` (unknown keys ignored)."""
        return _dataclass_from_dict(cls, data)


# --- Configuration ------------------------------------------------------------------------------


@dataclass(frozen=True)
class CarrierInput(JsonMixin):
    """Sensors of a generator (DATA_MODEL section 1.3).

    For a heat pump ``energy_entity`` is the electric counter; ``thermal_entity`` the
    thermal (heat) counter when the heat pump reports it.
    """

    energy_entity: str | None = None
    unit: CarrierUnit = CarrierUnit.KWH
    thermal_entity: str | None = None
    dhw_entity: str | None = None
    electric_entity: str | None = None


@dataclass(frozen=True)
class Conversion(JsonMixin):
    """Conversion parameters from carrier to heat (METHODS section 5)."""

    mode: ConversionMode = ConversionMode.FIXED_EFFICIENCY
    efficiency: float = 0.95
    heating_value: float = GAS_HS_KWH_PER_M3
    scop: float = 3.5
    cop: float = 3.0
    factor: float = 1.0
    #: Optional COP curve ``COP = cop_curve_a + cop_curve_b * t_mean`` (mode ``cop_curve``).
    cop_curve_a: float = 2.2
    cop_curve_b: float = 0.08


@dataclass(frozen=True)
class DhwConfig(JsonMixin):
    """Domestic hot water split configuration (METHODS section 6)."""

    mode: DhwMode = DhwMode.BASELINE
    #: Fixed DHW amount per day in carrier units (mode ``fixed``).
    fixed_per_day: float | None = None
    #: Summer window as ``MM-DD`` strings.
    summer_start: str = "06-01"
    summer_end: str = "08-31"


def default_unit(kind: GeneratorKind) -> CarrierUnit:
    """Default carrier unit for a generator kind."""
    if kind is GeneratorKind.GAS_BOILER:
        return CarrierUnit.M3
    if kind is GeneratorKind.DISTRICT_HEAT:
        return CarrierUnit.GJ
    return CarrierUnit.KWH


def default_conversion(kind: GeneratorKind) -> Conversion:
    """Default conversion per generator kind (CONFIG_FLOW step 4.3)."""
    if kind is GeneratorKind.GAS_BOILER:
        return Conversion(mode=ConversionMode.FIXED_EFFICIENCY, efficiency=0.95)
    if kind is GeneratorKind.HEAT_PUMP:
        return Conversion(mode=ConversionMode.COP_FIXED, scop=3.5)
    if kind is GeneratorKind.AIR_TO_AIR:
        return Conversion(mode=ConversionMode.COP_FIXED, cop=3.0)
    if kind is GeneratorKind.ELECTRIC_HEATER:
        return Conversion(mode=ConversionMode.FACTOR, factor=1.0)
    if kind is GeneratorKind.DISTRICT_HEAT:
        return Conversion(mode=ConversionMode.FIXED_EFFICIENCY, efficiency=1.0)
    return Conversion(mode=ConversionMode.FACTOR, factor=1.0)


def default_co2_factor(kind: GeneratorKind, unit: CarrierUnit) -> float | None:
    """Default CO2 factor in kg per carrier unit; None when no sensible default exists."""
    if kind is GeneratorKind.GAS_BOILER and unit is CarrierUnit.M3:
        return GAS_CO2_KG_PER_M3
    if kind in (GeneratorKind.HEAT_PUMP, GeneratorKind.ELECTRIC_HEATER, GeneratorKind.AIR_TO_AIR):
        return ELEC_CO2_KG_PER_KWH
    return None


@dataclass(frozen=True)
class Generator(JsonMixin):
    """A heat generator on a site (DATA_MODEL section 1.3)."""

    id: str
    name: str
    kind: GeneratorKind
    role: Role = Role.BOTH
    carrier: CarrierInput = field(default_factory=CarrierInput)
    conversion: Conversion = field(default_factory=Conversion)
    dhw: DhwConfig = field(default_factory=DhwConfig)
    price_entity: str | None = None
    co2_factor: float | None = None

    @classmethod
    def for_kind(
        cls,
        generator_id: str,
        name: str,
        kind: GeneratorKind,
        role: Role | None = None,
        **overrides: Any,
    ) -> Generator:
        """Create a generator with the per-kind defaults of the config flow."""
        if role is None:
            role = Role.SPACE if kind is GeneratorKind.AIR_TO_AIR else Role.BOTH
        params: dict[str, Any] = {
            "carrier": CarrierInput(unit=default_unit(kind)),
            "conversion": default_conversion(kind),
        }
        params.update(overrides)
        return cls(id=generator_id, name=name, kind=kind, role=role, **params)

    @property
    def is_heat_pump(self) -> bool:
        """True for the heat pump kinds (heat_pump and air_to_air)."""
        return self.kind in (GeneratorKind.HEAT_PUMP, GeneratorKind.AIR_TO_AIR)


@dataclass(frozen=True)
class WeatherSourceConfig(JsonMixin):
    """Weather source of a site (DATA_MODEL section 1.2)."""

    provider: Provider = Provider.KNMI
    station_id: str | None = None
    fallback: Provider = Provider.OPEN_METEO
    ha_entities: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SeasonConfig(JsonMixin):
    """Start of the heating season / gas year (default 1 October)."""

    start_month: int = 10
    start_day: int = 1


@dataclass(frozen=True)
class ClassicParams(JsonMixin):
    """Parameters of the classic (mindergas) method (METHODS section 4.1)."""

    base_temp: float = 18.0
    heating_limit: float = 18.0
    weighted: bool = True
    #: ``t_mean`` (default) or the name of an effective-temperature preset.
    t_ref: str = "t_mean"


@dataclass(frozen=True)
class PblParams(JsonMixin):
    """Parameters of the PBL / KEV-SJV method (METHODS section 4.3)."""

    parameter_set: str = "practical"
    wind_mode: str = "linear"
    include_sun: bool = False
    include_top: bool = False
    wind_sqrt_coef: float = PBL_WIND_SQRT_COEF


@dataclass(frozen=True)
class HouseParams(JsonMixin):
    """Parameters of the house-specific method and fit (METHODS sections 4.4 and 7)."""

    fit_wind: bool = True
    tac_weights: tuple[float, float] = PBL_TAC_WEIGHTS
    fallback_balance_temp: float = HOUSE_FALLBACK_BALANCE_TEMP


@dataclass(frozen=True)
class MethodConfig(JsonMixin):
    """Which methods are exposed and their parameters (DATA_MODEL section 1.5)."""

    enabled: list[str] = field(default_factory=lambda: ["classic", "pbl", "house"])
    classic: ClassicParams = field(default_factory=ClassicParams)
    pbl: PblParams = field(default_factory=PblParams)
    house: HouseParams = field(default_factory=HouseParams)
    primary: str = "house"


@dataclass(frozen=True)
class Measure(JsonMixin):
    """An energy-saving measure with its start date (DATA_MODEL section 1.4)."""

    id: str
    name: str
    date: date
    category: MeasureCategory = MeasureCategory.OTHER
    notes: str = ""


@dataclass(frozen=True)
class Site(JsonMixin):
    """A site (dwelling) with its configuration (DATA_MODEL section 1.1)."""

    id: str
    name: str = "Thuis"
    latitude: float = 52.10
    longitude: float = 5.18
    timezone: str = "Europe/Amsterdam"
    country: str = "NL"
    season: SeasonConfig = field(default_factory=SeasonConfig)
    methods: MethodConfig = field(default_factory=MethodConfig)
    backfill_years: int = 3
    climatology_years: int = 20
    weather: WeatherSourceConfig = field(default_factory=WeatherSourceConfig)
    generators: list[Generator] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)

    def generator(self, generator_id: str) -> Generator:
        """Return the generator with the given id."""
        for generator in self.generators:
            if generator.id == generator_id:
                return generator
        raise KeyError(generator_id)


# --- Facts --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyWeather(JsonMixin):
    """Weather of one local calendar day (METHODS section 2)."""

    date: date
    t_mean: float
    wind_mean: float | None = None
    radiation: float | None = None
    t_min: float | None = None
    t_max: float | None = None
    provisional: bool = False
    source: str = ""


@dataclass
class DailyEnergy(JsonMixin):
    """Energy and heat of one generator on one day (METHODS sections 5 and 6)."""

    date: date
    generator_id: str
    carrier_amount: float | None
    electric_kwh: float | None
    heat_total_kwh: float
    heat_dhw_kwh: float
    heat_space_kwh: float
    cop_day: float | None = None
    flags: set[Flag] = field(default_factory=set)


@dataclass
class DailyRecord(JsonMixin):
    """One row per site per day - the single source of truth (DATA_MODEL section 2.1)."""

    date: date
    site_id: str
    t_mean: float | None = None
    wind_mean: float | None = None
    radiation: float | None = None
    t_min: float | None = None
    t_max: float | None = None
    t_eff_knmi: float | None = None
    tac_pbl: float | None = None
    tac_house: float | None = None
    dd: dict[str, float] = field(default_factory=dict)
    heat_space_kwh: float = 0.0
    heat_dhw_kwh: float = 0.0
    electric_kwh: float = 0.0
    gas_m3: float = 0.0
    district_gj: float = 0.0
    heat_by_generator: dict[str, DailyEnergy] = field(default_factory=dict)
    share_heat_pump: float | None = None
    cost_eur: float | None = None
    co2_kg: float | None = None
    flags: set[Flag] = field(default_factory=set)

    @property
    def usable(self) -> bool:
        """True when the day carries no exclusion flag (METHODS section 10)."""
        return is_usable(self.flags)


@dataclass
class Climatology(JsonMixin):
    """Mean TAC, wind and degree days per day of year (METHODS section 8.1).

    Lists have 366 entries indexed by ``leap_doy - 1`` where ``leap_doy`` is the day of
    year in a leap-year calendar (Feb 29 = 60, Mar 1 = 61, Dec 31 = 366). Entries may be
    None when no data exists for that day of year.
    """

    site_id: str
    years: int
    tac_by_doy: list[float | None]
    wind_by_doy: list[float | None]
    dd_by_doy: dict[str, list[float | None]]
    computed_at: date
    #: Basis of ``tac_by_doy`` (preset name), ``house`` by default.
    tac_preset: str = "house"
    #: Number of source days per day of year (diagnostics).
    samples_by_doy: list[int] = field(default_factory=list)


# --- Derived ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Season(JsonMixin):
    """A heating season with label, start and end (inclusive)."""

    label: str
    start: date
    end: date

    def contains(self, day: date) -> bool:
        """True when ``day`` lies in the season (inclusive)."""
        return self.start <= day <= self.end


@dataclass(frozen=True)
class Period(JsonMixin):
    """An arbitrary date range, inclusive on both ends."""

    start: date
    end: date
    label: str | None = None

    def contains(self, day: date) -> bool:
        """True when ``day`` lies in the period (inclusive)."""
        return self.start <= day <= self.end

    @property
    def days(self) -> int:
        """Number of calendar days in the period."""
        return (self.end - self.start).days + 1

    @classmethod
    def from_season(cls, season: Season) -> Period:
        """Convert a :class:`Season` into a period."""
        return cls(start=season.start, end=season.end, label=season.label)


@dataclass(frozen=True)
class SignatureFit(JsonMixin):
    """Result of the energy-signature fit (METHODS section 7)."""

    site_id: str
    period: Period
    tac_preset: str
    balance_temp: float
    intercept_a: float
    slope_b: float
    wind_c: float | None
    ua_w_per_k: float
    r2: float
    rmse: float
    n_days: int
    n_heating_days: int
    ci95_slope: tuple[float, float]
    ci95_balance: tuple[float, float]
    fitted_at: datetime
    sse: float = 0.0
    outliers: list[date] = field(default_factory=list)

    def predict(self, tac: float, wind: float | None = None) -> float:
        """Model prediction ``a + b * max(0, T_b - tac) + c * wind`` in kWh per day."""
        heating = max(0.0, self.balance_temp - tac)
        value = self.intercept_a + self.slope_b * heating
        if self.wind_c is not None and wind is not None:
            value += self.wind_c * wind
        return value


@dataclass(frozen=True)
class Comparison(JsonMixin):
    """Comparison of two periods (METHODS sections 8.2-8.4)."""

    base: Period
    target: Period
    method: str
    k_base: float
    k_target: float
    delta_pct: float
    heat_base: float = 0.0
    heat_target: float = 0.0
    dd_base: float = 0.0
    dd_target: float = 0.0
    n_base: int = 0
    n_target: int = 0
    nac_base: float | None = None
    nac_target: float | None = None
    saving_pct: float | None = None
    ci95_saving: tuple[float, float] | None = None


@dataclass(frozen=True)
class Forecast(JsonMixin):
    """Forecast of the running season (METHODS section 8.5)."""

    season: Season
    method: str
    heat_space_ytd: float
    dd_ytd: float
    dd_remaining_clim: float
    heat_space_forecast: float
    per_generator: dict[str, float] = field(default_factory=dict)
    k_ytd: float | None = None
    days_ytd: int = 0
    days_remaining: int = 0
    heat_dhw_forecast: float = 0.0
    heat_space_forecast_fit: float | None = None
    last_date: date | None = None
