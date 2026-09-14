"""Diagnostics for Heatprint: config without secrets, last 30 day records, flags."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HeatprintConfigEntry
from .const import (
    CONF_CO2_ENTITY,
    CONF_DEMAND_ENTITY,
    CONF_DHW_ELECTRIC_ENTITY,
    CONF_DHW_ENTITY,
    CONF_ELECTRIC_ENTITY,
    CONF_ENERGY_ENTITY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MINDERGAS_TOKEN,
    CONF_PRICE_ENTITY,
    CONF_RADIATION_ENTITY,
    CONF_ROOM_TEMPERATURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_THERMAL_ENTITY,
    CONF_WIND_ENTITY,
    DATA_QUALITY_WINDOW_DAYS,
)

TO_REDACT = {
    CONF_MINDERGAS_TOKEN,
    CONF_DEMAND_ENTITY,
    CONF_ROOM_TEMPERATURE_ENTITY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ENERGY_ENTITY,
    CONF_THERMAL_ENTITY,
    CONF_ELECTRIC_ENTITY,
    CONF_DHW_ENTITY,
    CONF_DHW_ELECTRIC_ENTITY,
    CONF_PRICE_ENTITY,
    CONF_CO2_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_WIND_ENTITY,
    CONF_RADIATION_ENTITY,
    "recompute_token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HeatprintConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    end = coordinator.today - timedelta(days=1)
    start = end - timedelta(days=DATA_QUALITY_WINDOW_DAYS - 1)
    records = await coordinator.async_export_rows(start, end)
    store = coordinator.store
    data = coordinator.data
    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "subentries": [
                {
                    "subentry_id": subentry.subentry_id,
                    "subentry_type": subentry.subentry_type,
                    "title": subentry.title,
                    "data": async_redact_data(dict(subentry.data), TO_REDACT),
                }
                for subentry in entry.subentries.values()
            ],
        },
        "coordinator": {
            "summary": coordinator.summary(),
            "last_update_success": coordinator.last_update_success,
            "primary_method": data.primary_method if data else None,
            "season": {
                "label": data.season.label,
                "days": data.season.days,
                "dd": data.season.dd,
                "heat_space_kwh": data.season.heat_space_kwh,
                "heat_dhw_kwh": data.season.heat_dhw_kwh,
                "share_heat_pump": data.season.share_heat_pump,
            }
            if data
            else None,
            "data_quality": {
                "usable_share": data.data_quality.usable_share,
                "gap_days": data.data_quality.gap_days,
                "flag_counts": data.data_quality.flag_counts,
                "open_health_checks": data.data_quality.open_health_checks,
            }
            if data
            else None,
        },
        "store": {
            "meta": async_redact_data(dict(store.data.get("meta", {})), TO_REDACT),
            "fits": store.fits,
            "room_fits": store.all_latest_room_fits(),
            "baselines": store.baselines,
            "forecast": store.forecast,
            "climatology_present": store.climatology is not None,
            "weather_cache_days": len(store.data.get("weather_cache", {})),
            "flag_days": len(store.data.get("flags", {})),
            "imported_generators": {
                generator_id: len(days)
                for generator_id, days in store.data.get("imported", {}).items()
            },
        },
        "records_last_30_days": records,
        "flags_last_30_days": {
            day.isoformat(): flags for day, flags in store.flags_between(start, end).items()
        },
    }
