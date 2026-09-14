"""The Heatprint integration: weather-corrected heating analytics.

One config entry per site. The heavy lifting happens in the pure-Python core
(heatprint_core); this package configures, reads the recorder, writes external
statistics and exposes entities and services.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# HACS only copies this folder; heatprint_core is bundled here, not on PyPI.
_INTEGRATION_DIR = str(Path(__file__).resolve().parent)
if _INTEGRATION_DIR not in sys.path:
    sys.path.insert(0, _INTEGRATION_DIR)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import HeatprintCoordinator
from .dashboard import async_ensure_rooms_dashboard, async_setup_entry_dashboard
from .device_registry_ux import align_heatprint_devices
from .room_sync import sync_rooms_if_auto
from .services import async_setup_services
from .store import HeatprintStore

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

HeatprintConfigEntry = ConfigEntry[HeatprintCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services once."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HeatprintConfigEntry) -> bool:
    """Set up a Heatprint site from a config entry."""
    if not hasattr(entry, "subentries"):
        # Config subentries need Home Assistant 2026.9+ (see hacs.json).
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="ha_too_old")

    rooms_plan = sync_rooms_if_auto(hass, entry)

    coordinator = HeatprintCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    try:
        align_heatprint_devices(hass, coordinator)
    except Exception:  # noqa: BLE001 - area/name alignment must not fail setup
        _LOGGER.exception("Could not align Heatprint device areas or legacy names")
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    coordinator.async_start()
    await async_setup_entry_dashboard(hass, entry)
    if rooms_plan.changed:
        try:
            await async_ensure_rooms_dashboard(hass, entry, recreate=True)
        except Exception:  # noqa: BLE001 - dashboard must not fail the integration
            _LOGGER.exception("Could not refresh the Heatprint rooms dashboard after room sync")
    return True


async def _async_update_listener(hass: HomeAssistant, entry: HeatprintConfigEntry) -> None:
    """Reload the entry when options, data or subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HeatprintConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the JSON store when the entry is deleted (statistics are kept, ADR 0003)."""
    store = HeatprintStore(hass, entry.entry_id)
    await store.async_remove()


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries (no-op for version 1)."""
    if entry.version > 1:
        _LOGGER.error("Cannot downgrade Heatprint config entry from version %s", entry.version)
        return False
    return True
