"""Binary sensor entities for Heatprint (DATA_MODEL 4)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HeatprintConfigEntry
from .const import BINARY_SENSOR_DATA_GAP, DATA_GAP_DAYS
from .coordinator import HeatprintCoordinator
from .sensor import site_device_info

PARALLEL_UPDATES = 0

DATA_GAP_DESCRIPTION = BinarySensorEntityDescription(
    key=BINARY_SENSOR_DATA_GAP,
    translation_key=BINARY_SENSOR_DATA_GAP,
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatprintConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the data gap binary sensor."""
    async_add_entities([HeatprintDataGapSensor(entry.runtime_data)])


class HeatprintDataGapSensor(CoordinatorEntity[HeatprintCoordinator], BinarySensorEntity):
    """On when more than 3 days in a row lack usable data."""

    entity_description = DATA_GAP_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: HeatprintCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{BINARY_SENSOR_DATA_GAP}"
        self._attr_device_info = site_device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        """Return True when the current gap exceeds the threshold."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.data_quality.gap_days > DATA_GAP_DAYS

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the gap length and the last usable day."""
        if self.coordinator.data is None:
            return None
        quality = self.coordinator.data.data_quality
        return {
            "gap_days": quality.gap_days,
            "threshold_days": DATA_GAP_DAYS,
            "last_usable_day": quality.last_usable.isoformat() if quality.last_usable else None,
        }
