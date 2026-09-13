"""Services (actions) of Heatprint (DATA_MODEL 5).

All services take an ``entry_id`` (config entry selector) and delegate to the
coordinator of that site. Files are only read from and written to
``<config>/heatprint``. Responses follow ``SupportsResponse``: analyses return
their result (ONLY), mutating services optionally return a summary.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_BASE_END,
    ATTR_BASE_START,
    ATTR_CSV,
    ATTR_DATE,
    ATTR_DATE_COLUMN,
    ATTR_DATE_FORMAT,
    ATTR_DECIMAL,
    ATTR_DELIMITER,
    ATTR_END,
    ATTR_ENTRY_ID,
    ATTR_FIT_WIND,
    ATTR_FROM_DATE,
    ATTR_GENERATOR_ID,
    ATTR_MAPPING,
    ATTR_MEASURE_ID,
    ATTR_METHOD,
    ATTR_PATH,
    ATTR_READING_COLUMN,
    ATTR_SEASON,
    ATTR_START,
    ATTR_TAC_PRESET,
    ATTR_TARGET,
    ATTR_TARGET_END,
    ATTR_TARGET_START,
    ATTR_UNIT,
    DOMAIN,
    EXPORT_DIRECTORY,
    GJ_TO_KWH,
    IMPORT_UNITS,
    METHODS,
    PUSH_TARGET_MINDERGAS,
    PUSH_TARGETS,
    SERVICE_CLEAR_STATISTICS,
    SERVICE_COMPARE_PERIODS,
    SERVICE_CREATE_DASHBOARD,
    SERVICE_EXPORT_DAILY,
    SERVICE_FIT_SIGNATURE,
    SERVICE_FORECAST,
    SERVICE_IMPORT_READINGS,
    SERVICE_MEASURE_EFFECT,
    SERVICE_PUSH_READING,
    SERVICE_RECOMPUTE,
    TAC_PRESETS,
    UNIT_GJ,
)
from .core_api import CoreError, parse_readings_csv, season_from_label
from .mindergas import MindergasError

if TYPE_CHECKING:
    from .coordinator import HeatprintCoordinator

_LOGGER = logging.getLogger(__name__)

COMPARE_METHODS = [*METHODS, "signature"]

MAPPING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DATE_COLUMN, default="datum"): cv.string,
        vol.Optional(ATTR_READING_COLUMN, default="stand"): cv.string,
        vol.Optional(ATTR_DATE_FORMAT, default="%d-%m-%Y"): cv.string,
        vol.Optional(ATTR_DECIMAL, default=","): cv.string,
        vol.Optional(ATTR_DELIMITER, default=";"): cv.string,
    }
)

IMPORT_READINGS_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_GENERATOR_ID): cv.string,
            vol.Optional(ATTR_CSV): cv.string,
            vol.Optional(ATTR_PATH): cv.string,
            vol.Optional(ATTR_MAPPING, default={}): MAPPING_SCHEMA,
            vol.Optional(ATTR_UNIT): vol.In(IMPORT_UNITS),
        }
    ),
    cv.has_at_least_one_key(ATTR_CSV, ATTR_PATH),
)
RECOMPUTE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTRY_ID): cv.string, vol.Required(ATTR_FROM_DATE): cv.date}
)
FIT_SIGNATURE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_START): cv.date,
        vol.Optional(ATTR_END): cv.date,
        vol.Optional(ATTR_SEASON): cv.string,
        vol.Optional(ATTR_TAC_PRESET, default="house"): vol.In(TAC_PRESETS),
        vol.Optional(ATTR_FIT_WIND): cv.boolean,
    }
)
COMPARE_PERIODS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_BASE_START): cv.date,
        vol.Required(ATTR_BASE_END): cv.date,
        vol.Required(ATTR_TARGET_START): cv.date,
        vol.Required(ATTR_TARGET_END): cv.date,
        vol.Optional(ATTR_METHOD, default="signature"): vol.In(COMPARE_METHODS),
    }
)
MEASURE_EFFECT_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTRY_ID): cv.string, vol.Required(ATTR_MEASURE_ID): cv.string}
)
FORECAST_SCHEMA = vol.Schema({vol.Required(ATTR_ENTRY_ID): cv.string})
EXPORT_DAILY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_START): cv.date,
        vol.Required(ATTR_END): cv.date,
        vol.Optional(ATTR_PATH): cv.string,
    }
)
PUSH_READING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_GENERATOR_ID): cv.string,
        vol.Optional(ATTR_TARGET, default=PUSH_TARGET_MINDERGAS): vol.In(PUSH_TARGETS),
        vol.Optional(ATTR_DATE): cv.date,
    }
)
CLEAR_STATISTICS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_GENERATOR_ID): cv.string,
    }
)
CREATE_DASHBOARD_SCHEMA = vol.Schema({vol.Required(ATTR_ENTRY_ID): cv.string})


@callback
def _get_coordinator(hass: HomeAssistant, entry_id: str) -> HeatprintCoordinator:
    """Resolve the coordinator of a loaded Heatprint config entry."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"entry_id": entry_id},
        )
    return entry.runtime_data


def _base_directory(hass: HomeAssistant) -> Path:
    """Return the directory Heatprint may read from and write to."""
    return Path(hass.config.path(EXPORT_DIRECTORY))


def _resolve_path(hass: HomeAssistant, path: str) -> Path:
    """Resolve a user supplied path inside <config>/heatprint or raise."""
    base = _base_directory(hass).resolve()
    candidate = Path(path)
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="path_not_allowed",
            translation_placeholders={"path": path, "base": str(base)},
        )
    return resolved


def _read_text(path: Path) -> str:
    """Read a text file (executor)."""
    return path.read_text(encoding="utf-8-sig")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> int:
    """Write rows as CSV (executor); returns the number of rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return len(rows)


def _period(start: date, end: date) -> tuple[date, date]:
    """Validate that start <= end."""
    if start > end:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_period")
    return start, end


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Heatprint services (called once from async_setup)."""

    async def handle_import_readings(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        if ATTR_CSV in call.data:
            text = call.data[ATTR_CSV]
        else:
            path = _resolve_path(hass, call.data[ATTR_PATH])
            try:
                text = await hass.async_add_executor_job(_read_text, path)
            except OSError as err:
                raise HomeAssistantError(f"Cannot read {path}: {err}") from err
        generator = coordinator.generator(call.data[ATTR_GENERATOR_ID])
        unit = call.data.get(ATTR_UNIT) or generator.unit
        try:
            readings = await hass.async_add_executor_job(
                parse_readings_csv, text, call.data[ATTR_MAPPING]
            )
        except (CoreError, ValueError, KeyError) as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="csv_invalid",
                translation_placeholders={"error": str(err)},
            ) from err
        if unit == UNIT_GJ:
            # Recorder reads are normalised to kWh; imported GJ readings follow suit.
            readings = [(stamp, value * GJ_TO_KWH) for stamp, value in readings]
        result = await coordinator.async_import_readings(generator.generator_id, readings)
        return result if call.return_response else None

    async def handle_recompute(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        days = await coordinator.async_recompute(call.data[ATTR_FROM_DATE])
        return {"days": days} if call.return_response else None

    async def handle_fit_signature(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        if ATTR_SEASON in call.data:
            try:
                season = season_from_label(coordinator.entry, call.data[ATTR_SEASON])
            except ValueError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="invalid_period"
                ) from err
            # Today has no complete day record yet; the running season ends yesterday.
            start, end = season.start, min(season.end, coordinator.today - timedelta(days=1))
        elif ATTR_START in call.data and ATTR_END in call.data:
            start, end = _period(call.data[ATTR_START], call.data[ATTR_END])
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="period_required"
            )
        try:
            return await coordinator.async_fit_signature(
                start, end, call.data[ATTR_TAC_PRESET], call.data.get(ATTR_FIT_WIND)
            )
        except CoreError as err:
            raise HomeAssistantError(f"Fit failed: {err}") from err

    async def handle_compare_periods(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        base = _period(call.data[ATTR_BASE_START], call.data[ATTR_BASE_END])
        target = _period(call.data[ATTR_TARGET_START], call.data[ATTR_TARGET_END])
        try:
            return await coordinator.async_compare_periods(base, target, call.data[ATTR_METHOD])
        except CoreError as err:
            raise HomeAssistantError(f"Comparison failed: {err}") from err

    async def handle_measure_effect(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        try:
            return await coordinator.async_measure_effect(call.data[ATTR_MEASURE_ID])
        except CoreError as err:
            raise HomeAssistantError(f"Measure effect failed: {err}") from err

    async def handle_forecast(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        return await coordinator.async_forecast()

    async def handle_export_daily(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        start, end = _period(call.data[ATTR_START], call.data[ATTR_END])
        default_name = f"heatprint_{coordinator.site_id}_{start.isoformat()}_{end.isoformat()}.csv"
        path = _resolve_path(hass, call.data.get(ATTR_PATH) or default_name)
        rows = await coordinator.async_export_rows(start, end)
        try:
            count = await hass.async_add_executor_job(_write_csv, path, rows)
        except OSError as err:
            raise HomeAssistantError(f"Cannot write {path}: {err}") from err
        return {"path": str(path), "rows": count} if call.return_response else None

    async def handle_push_reading(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        day = call.data.get(ATTR_DATE) or coordinator.today
        try:
            result = await coordinator.async_push_reading(call.data[ATTR_GENERATOR_ID], day)
        except MindergasError as err:
            raise HomeAssistantError(str(err)) from err
        return result if call.return_response else None

    async def handle_clear_statistics(call: ServiceCall) -> ServiceResponse:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        result = await coordinator.async_clear_statistics(call.data.get(ATTR_GENERATOR_ID))
        return result if call.return_response else None

    async def handle_create_dashboard(call: ServiceCall) -> ServiceResponse:
        from .dashboard import async_ensure_overview_dashboard

        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        result = await async_ensure_overview_dashboard(hass, coordinator.entry, recreate=True)
        return result if call.return_response else None

    registrations: list[tuple[str, Any, vol.Schema, SupportsResponse]] = [
        (
            SERVICE_IMPORT_READINGS,
            handle_import_readings,
            IMPORT_READINGS_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (SERVICE_RECOMPUTE, handle_recompute, RECOMPUTE_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_FIT_SIGNATURE, handle_fit_signature, FIT_SIGNATURE_SCHEMA, SupportsResponse.ONLY),
        (
            SERVICE_COMPARE_PERIODS,
            handle_compare_periods,
            COMPARE_PERIODS_SCHEMA,
            SupportsResponse.ONLY,
        ),
        (
            SERVICE_MEASURE_EFFECT,
            handle_measure_effect,
            MEASURE_EFFECT_SCHEMA,
            SupportsResponse.ONLY,
        ),
        (SERVICE_FORECAST, handle_forecast, FORECAST_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_EXPORT_DAILY, handle_export_daily, EXPORT_DAILY_SCHEMA, SupportsResponse.OPTIONAL),
        (SERVICE_PUSH_READING, handle_push_reading, PUSH_READING_SCHEMA, SupportsResponse.OPTIONAL),
        (
            SERVICE_CLEAR_STATISTICS,
            handle_clear_statistics,
            CLEAR_STATISTICS_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
        (
            SERVICE_CREATE_DASHBOARD,
            handle_create_dashboard,
            CREATE_DASHBOARD_SCHEMA,
            SupportsResponse.OPTIONAL,
        ),
    ]
    for name, handler, schema, supports_response in registrations:
        if hass.services.has_service(DOMAIN, name):
            continue
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=supports_response
        )
