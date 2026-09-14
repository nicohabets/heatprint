"""Repair issues and first-run notifications (weather check + METHODS §14)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    ISSUE_HEALTH_PREFIX,
    ISSUE_WEATHER_CHECK,
    NOTIFICATION_WEATHER_CHECK,
)

_LOGGER = logging.getLogger(__name__)

_WEATHER_ERROR_LABELS = {
    "cannot_connect": "cannot_connect",
    "no_data_for_station": "no_data_for_station",
}


def weather_error_label(error: str) -> str:
    """Return a stable, user-facing key for a weather-check failure."""
    return _WEATHER_ERROR_LABELS.get(error, error)


@callback
def async_raise_weather_check_failed(
    hass: HomeAssistant,
    *,
    site_id: str,
    site_name: str,
    error: str,
    weather_label: str,
) -> None:
    """Surface a non-blocking first-run weather failure as a repair + notification."""
    issue_id = ISSUE_WEATHER_CHECK.format(site_id=site_id)
    notification_id = NOTIFICATION_WEATHER_CHECK.format(site_id=site_id)
    error_key = weather_error_label(error)
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="weather_check_failed",
        translation_placeholders={
            "site": site_name,
            "error": error_key,
            "weather": weather_label,
        },
    )
    persistent_notification.async_create(
        hass,
        (
            f"The first-run weather check for {site_name} failed ({error_key}) "
            f"using {weather_label}. Heatprint was still created and will retry. "
            "Use Reconfigure to pick another station or provider if this persists."
        ),
        title=f"Heatprint {site_name}: weather source not reachable yet",
        notification_id=notification_id,
    )
    _LOGGER.warning(
        "Weather check at first-run failed for %s (%s); setup continues",
        site_name,
        error_key,
    )


@callback
def async_clear_weather_check_failed(hass: HomeAssistant, site_id: str) -> None:
    """Dismiss the weather-check repair and notification once weather works."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_WEATHER_CHECK.format(site_id=site_id))
    persistent_notification.async_dismiss(hass, NOTIFICATION_WEATHER_CHECK.format(site_id=site_id))


@callback
def async_sync_health_checks(
    hass: HomeAssistant,
    *,
    site_id: str,
    site_name: str,
    findings: Sequence[Any],
) -> None:
    """Open a repair per firing check; close those that no longer fire."""
    wanted = {finding.issue_id(site_id): finding for finding in findings}
    registry = ir.async_get(hass)
    existing = [issue_id for (domain, issue_id) in registry.issues if domain == DOMAIN]
    prefix = ISSUE_HEALTH_PREFIX.format(site_id=site_id)
    for issue_id in existing:
        if issue_id.startswith(prefix) and issue_id not in wanted:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
    for issue_id, finding in wanted.items():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"health_{finding.check.value}",
            translation_placeholders={
                "site": site_name,
                "source": finding.source_name,
            },
        )
