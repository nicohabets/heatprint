"""Sensor entities for Heatprint (DATA_MODEL 4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HeatprintConfigEntry
from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL_SITE,
    SENSOR_BALANCE_TEMPERATURE,
    SENSOR_COP_YESTERDAY,
    SENSOR_DATA_QUALITY,
    SENSOR_DEGREE_DAYS_SEASON,
    SENSOR_DEGREE_DAYS_YESTERDAY,
    SENSOR_DHW_BASELINE,
    SENSOR_EFFECTIVE_TEMPERATURE,
    SENSOR_FIT_QUALITY,
    SENSOR_FORECAST_ELECTRIC_SEASON,
    SENSOR_FORECAST_GAS_SEASON,
    SENSOR_FORECAST_HEAT_SEASON,
    SENSOR_GAS_PER_DEGREE_DAY,
    SENSOR_GENERATOR_HEAT_DHW_SEASON,
    SENSOR_GENERATOR_HEAT_SPACE_SEASON,
    SENSOR_GENERATOR_SHARE_SEASON,
    SENSOR_HEAT_DHW_SEASON,
    SENSOR_HEAT_LOSS_COEFFICIENT,
    SENSOR_HEAT_PER_DEGREE_DAY,
    SENSOR_HEAT_PUMP_SHARE_SEASON,
    SENSOR_HEAT_SPACE_SEASON,
    SENSOR_HEAT_SPACE_YESTERDAY,
    SENSOR_LAST_WEATHER_UPDATE,
    SUBENTRY_TYPE_GENERATOR,
    UNIT_DEGREE_DAYS,
    UNIT_KWH_PER_DAY,
    UNIT_KWH_PER_K,
    UNIT_M3_PER_K,
    UNIT_PERCENT,
    UNIT_W_PER_K,
)
from .coordinator import GeneratorAggregate, HeatprintCoordinator, HeatprintData
from .core_api import GeneratorConfig

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HeatprintSensorDescription(SensorEntityDescription):
    """Describes a site sensor and how to read it from the snapshot."""

    value_fn: Callable[[HeatprintData], StateType | datetime]
    attributes_fn: Callable[[HeatprintData], dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class HeatprintGeneratorSensorDescription(SensorEntityDescription):
    """Describes a per-generator sensor."""

    value_fn: Callable[[GeneratorAggregate], StateType]


def _fit_value(key: str) -> Callable[[HeatprintData], StateType]:
    def _value(data: HeatprintData) -> StateType:
        if not data.fit:
            return None
        value = data.fit.get(key)
        return float(value) if value is not None else None

    return _value


def _forecast_value(key: str) -> Callable[[HeatprintData], StateType]:
    def _value(data: HeatprintData) -> StateType:
        if not data.forecast:
            return None
        value = data.forecast.get(key)
        return float(value) if value is not None else None

    return _value


def _percent(value: float | None) -> StateType:
    return round(value * 100, 1) if value is not None else None


def _dd_attributes(data: HeatprintData) -> dict[str, Any]:
    latest = data.latest
    attributes: dict[str, Any] = {"method": data.primary_method}
    if latest:
        attributes.update({f"dd_{method}": value for method, value in latest.dd.items()})
        attributes["date"] = latest.date.isoformat()
        attributes["provisional"] = latest.provisional
    return attributes


def _season_dd_attributes(data: HeatprintData) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "method": data.primary_method,
        "season": data.season.label,
        "season_start": data.season.start.isoformat(),
        "season_end": data.season.end.isoformat(),
        "days": data.season.days,
    }
    attributes.update({f"dd_{method}": round(value, 2) for method, value in data.season.dd.items()})
    return attributes


def _heat_per_dd_attributes(data: HeatprintData) -> dict[str, Any]:
    attributes: dict[str, Any] = {"method": data.primary_method, "season": data.season.label}
    attributes.update(
        {
            f"kwh_per_k_{method}": round(value, 4)
            for method, value in data.season.heat_per_dd.items()
        }
    )
    return attributes


def _fit_attributes(data: HeatprintData) -> dict[str, Any]:
    if not data.fit:
        return {}
    fit = data.fit
    return {
        "n_days": fit.get("n_days"),
        "rmse": fit.get("rmse"),
        "ci95_slope": fit.get("ci95_slope"),
        "ci95_balance": fit.get("ci95_balance"),
        "intercept_a": fit.get("intercept_a"),
        "wind_c": fit.get("wind_c"),
        "period_start": fit.get("period_start"),
        "period_end": fit.get("period_end"),
        "fitted_at": fit.get("fitted_at"),
        "tac_preset": fit.get("tac_preset"),
    }


def _dhw_attributes(data: HeatprintData) -> dict[str, Any]:
    return {f"baseline_{generator_id}": value for generator_id, value in data.dhw_baseline.items()}


def _quality_attributes(data: HeatprintData) -> dict[str, Any]:
    quality = data.data_quality
    attributes: dict[str, Any] = {
        "gap_days": quality.gap_days,
        "last_usable_day": quality.last_usable.isoformat() if quality.last_usable else None,
    }
    attributes.update(
        {f"flag_{flag.lower()}": count for flag, count in quality.flag_counts.items()}
    )
    if data.latest:
        attributes["latest_flags"] = data.latest.flags
    return attributes


def _forecast_attributes(data: HeatprintData) -> dict[str, Any]:
    if not data.forecast:
        return {}
    forecast = data.forecast
    return {
        "season": forecast.get("season"),
        "heat_space_ytd": forecast.get("heat_space_ytd"),
        "dd_ytd": forecast.get("dd_ytd"),
        "dd_remaining_clim": forecast.get("dd_remaining_clim"),
        "per_generator": forecast.get("per_generator"),
        "method": data.primary_method,
    }


SITE_SENSORS: tuple[HeatprintSensorDescription, ...] = (
    HeatprintSensorDescription(
        key=SENSOR_EFFECTIVE_TEMPERATURE,
        translation_key=SENSOR_EFFECTIVE_TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.latest.tac_primary if data.latest else None,
        attributes_fn=lambda data: {
            "t_mean": data.latest.t_mean if data.latest else None,
            "date": data.latest.date.isoformat() if data.latest else None,
            "method": data.primary_method,
        },
    ),
    HeatprintSensorDescription(
        key=SENSOR_DEGREE_DAYS_YESTERDAY,
        translation_key=SENSOR_DEGREE_DAYS_YESTERDAY,
        native_unit_of_measurement=UNIT_DEGREE_DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:snowflake-thermometer",
        suggested_display_precision=2,
        value_fn=lambda data: data.latest.dd.get(data.primary_method) if data.latest else None,
        attributes_fn=_dd_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_DEGREE_DAYS_SEASON,
        translation_key=SENSOR_DEGREE_DAYS_SEASON,
        native_unit_of_measurement=UNIT_DEGREE_DAYS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:sigma",
        suggested_display_precision=1,
        value_fn=lambda data: data.season.dd.get(data.primary_method),
        attributes_fn=_season_dd_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_HEAT_SPACE_YESTERDAY,
        translation_key=SENSOR_HEAT_SPACE_YESTERDAY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1,
        value_fn=lambda data: data.latest.heat_space_kwh if data.latest else None,
        attributes_fn=lambda data: {
            "heat_dhw_kwh": data.latest.heat_dhw_kwh if data.latest else None,
            "date": data.latest.date.isoformat() if data.latest else None,
            "flags": data.latest.flags if data.latest else [],
        },
    ),
    HeatprintSensorDescription(
        key=SENSOR_HEAT_SPACE_SEASON,
        translation_key=SENSOR_HEAT_SPACE_SEASON,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.season.heat_space_kwh,
        attributes_fn=lambda data: {"season": data.season.label, "days": data.season.days},
    ),
    HeatprintSensorDescription(
        key=SENSOR_HEAT_DHW_SEASON,
        translation_key=SENSOR_HEAT_DHW_SEASON,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.season.heat_dhw_kwh,
        attributes_fn=lambda data: {"season": data.season.label},
    ),
    HeatprintSensorDescription(
        key=SENSOR_HEAT_PER_DEGREE_DAY,
        translation_key=SENSOR_HEAT_PER_DEGREE_DAY,
        native_unit_of_measurement=UNIT_KWH_PER_K,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-thermometer",
        suggested_display_precision=3,
        value_fn=lambda data: data.season.heat_per_dd.get(data.primary_method),
        attributes_fn=_heat_per_dd_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_GAS_PER_DEGREE_DAY,
        translation_key=SENSOR_GAS_PER_DEGREE_DAY,
        native_unit_of_measurement=UNIT_M3_PER_K,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
        suggested_display_precision=4,
        value_fn=lambda data: data.season.gas_per_dd_classic,
        attributes_fn=lambda data: {
            "method": "classic",
            "gas_m3": round(data.season.gas_m3, 2),
            "dd_classic": round(data.season.dd.get("classic", 0.0), 2),
        },
    ),
    HeatprintSensorDescription(
        key=SENSOR_HEAT_PUMP_SHARE_SEASON,
        translation_key=SENSOR_HEAT_PUMP_SHARE_SEASON,
        native_unit_of_measurement=UNIT_PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:heat-pump",
        suggested_display_precision=1,
        value_fn=lambda data: _percent(data.season.share_heat_pump),
        attributes_fn=lambda data: {"electric_hp_kwh": round(data.season.electric_hp_kwh, 1)},
    ),
    HeatprintSensorDescription(
        key=SENSOR_COP_YESTERDAY,
        translation_key=SENSOR_COP_YESTERDAY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:heat-pump-outline",
        suggested_display_precision=2,
        value_fn=lambda data: data.latest.cop if data.latest else None,
    ),
    HeatprintSensorDescription(
        key=SENSOR_HEAT_LOSS_COEFFICIENT,
        translation_key=SENSOR_HEAT_LOSS_COEFFICIENT,
        native_unit_of_measurement=UNIT_W_PER_K,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-export-outline",
        suggested_display_precision=0,
        value_fn=_fit_value("ua_w_per_k"),
        attributes_fn=lambda data: {
            "slope_b_kwh_per_k_day": data.fit.get("slope_b") if data.fit else None
        },
    ),
    HeatprintSensorDescription(
        key=SENSOR_BALANCE_TEMPERATURE,
        translation_key=SENSOR_BALANCE_TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_fit_value("balance_temp"),
    ),
    HeatprintSensorDescription(
        key=SENSOR_FIT_QUALITY,
        translation_key=SENSOR_FIT_QUALITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve",
        suggested_display_precision=3,
        value_fn=_fit_value("r2"),
        attributes_fn=_fit_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_FORECAST_HEAT_SEASON,
        translation_key=SENSOR_FORECAST_HEAT_SEASON,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
        value_fn=_forecast_value("heat_space_forecast"),
        attributes_fn=_forecast_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_FORECAST_GAS_SEASON,
        translation_key=SENSOR_FORECAST_GAS_SEASON,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        suggested_display_precision=0,
        value_fn=_forecast_value("gas_m3_forecast"),
    ),
    HeatprintSensorDescription(
        key=SENSOR_FORECAST_ELECTRIC_SEASON,
        translation_key=SENSOR_FORECAST_ELECTRIC_SEASON,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
        value_fn=_forecast_value("electric_kwh_forecast"),
    ),
    HeatprintSensorDescription(
        key=SENSOR_DHW_BASELINE,
        translation_key=SENSOR_DHW_BASELINE,
        native_unit_of_measurement=UNIT_KWH_PER_DAY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-boiler",
        suggested_display_precision=2,
        value_fn=lambda data: (
            round(sum(data.dhw_baseline.values()), 3) if data.dhw_baseline else None
        ),
        attributes_fn=_dhw_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_DATA_QUALITY,
        translation_key=SENSOR_DATA_QUALITY,
        native_unit_of_measurement=UNIT_PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:check-decagram-outline",
        suggested_display_precision=0,
        value_fn=lambda data: _percent(data.data_quality.usable_share),
        attributes_fn=_quality_attributes,
    ),
    HeatprintSensorDescription(
        key=SENSOR_LAST_WEATHER_UPDATE,
        translation_key=SENSOR_LAST_WEATHER_UPDATE,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_weather_update,
    ),
)

GENERATOR_SENSORS: tuple[HeatprintGeneratorSensorDescription, ...] = (
    HeatprintGeneratorSensorDescription(
        key=SENSOR_GENERATOR_HEAT_SPACE_SEASON,
        translation_key=SENSOR_GENERATOR_HEAT_SPACE_SEASON,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda aggregate: aggregate.heat_space_kwh,
    ),
    HeatprintGeneratorSensorDescription(
        key=SENSOR_GENERATOR_HEAT_DHW_SEASON,
        translation_key=SENSOR_GENERATOR_HEAT_DHW_SEASON,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda aggregate: aggregate.heat_dhw_kwh,
    ),
    HeatprintGeneratorSensorDescription(
        key=SENSOR_GENERATOR_SHARE_SEASON,
        translation_key=SENSOR_GENERATOR_SHARE_SEASON,
        native_unit_of_measurement=UNIT_PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-pie",
        suggested_display_precision=1,
        value_fn=lambda aggregate: _percent(aggregate.share),
    ),
)


def site_device_info(coordinator: HeatprintCoordinator) -> DeviceInfo:
    """Return the device info of the site device."""
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.entry.entry_id)},
        name=coordinator.site_name,
        manufacturer=MANUFACTURER,
        model=MODEL_SITE,
        entry_type=DeviceEntryType.SERVICE,
    )


def generator_device_info(
    coordinator: HeatprintCoordinator, generator: GeneratorConfig
) -> DeviceInfo:
    """Return the device info of a generator device (child of the site device)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{generator.generator_id}")},
        name=f"{coordinator.site_name} {generator.name}",
        manufacturer=MANUFACTURER,
        model=generator.kind.replace("_", " ").title(),
        via_device=(DOMAIN, coordinator.entry.entry_id),
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatprintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the site sensors and one set of sensors per generator subentry."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeatprintSiteSensor(coordinator, description) for description in SITE_SENSORS
    )
    for generator in coordinator.generators:
        subentry = entry.subentries.get(generator.subentry_id or "")
        if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_GENERATOR:
            continue
        async_add_entities(
            (
                HeatprintGeneratorSensor(coordinator, generator, description)
                for description in GENERATOR_SENSORS
            ),
            config_subentry_id=subentry.subentry_id,
        )


class HeatprintSiteSensor(CoordinatorEntity[HeatprintCoordinator], SensorEntity):
    """A site-level sensor reading from the coordinator snapshot."""

    entity_description: HeatprintSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: HeatprintCoordinator, description: HeatprintSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = site_device_info(coordinator)

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the multi-method values and context."""
        if self.coordinator.data is None or self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class HeatprintGeneratorSensor(CoordinatorEntity[HeatprintCoordinator], SensorEntity):
    """A per-generator sensor on a child device."""

    entity_description: HeatprintGeneratorSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HeatprintCoordinator,
        generator: GeneratorConfig,
        description: HeatprintGeneratorSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._generator_id = generator.generator_id
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{generator.generator_id}_{description.key}"
        )
        self._attr_device_info = generator_device_info(coordinator, generator)

    @callback
    def _aggregate(self) -> GeneratorAggregate | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.season.per_generator.get(self._generator_id)

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        aggregate = self._aggregate()
        if aggregate is None:
            return None
        return self.entity_description.value_fn(aggregate)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return season context."""
        if self.coordinator.data is None:
            return None
        return {"season": self.coordinator.data.season.label, "generator_id": self._generator_id}
