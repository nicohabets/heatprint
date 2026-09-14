"""Device registry UX: Heatprint-branded names and room area assignment.

Home Assistant-free planning so the naming and area rules can be unit-tested
without importing Home Assistant. Applying a plan talks to the device registry.

Room (and generator) devices are named ``Heatprint {part}``, not
``{site_name} {part}``. The site/home name (e.g. ``Thuis``) stays on the config
entry and the site device. Room devices also get the HA area they were
discovered from: ``suggested_area`` on first create, and a best-effort fill of
empty ``area_id`` on reload. User-assigned areas and custom ``name_by_user``
values are left alone; only the old auto name ``{site} {room}`` is cleared.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

# Keep in lockstep with const.py (this module must stay HA-free).
DOMAIN = "heatprint"
INTEGRATION_NAME = "Heatprint"

_LOGGER = logging.getLogger(__name__)


def branded_device_name(part: str | None) -> str:
    """Return ``Heatprint {part}`` for room and generator devices."""
    cleaned = (part or "").strip()
    return f"{INTEGRATION_NAME} {cleaned}" if cleaned else INTEGRATION_NAME


def is_legacy_auto_device_name(
    name_by_user: str | None, site_name: str | None, part_name: str | None
) -> bool:
    """True when ``name_by_user`` is the old ``{site_name} {part}`` auto name."""
    user = (name_by_user or "").strip()
    site = (site_name or "").strip()
    part = (part_name or "").strip()
    if not user or not site or not part:
        return False
    return user == f"{site} {part}"


def device_identifier(entry_id: str, suffix: str) -> str:
    """Return the device-registry identifier value for a child device."""
    return f"{entry_id}_{suffix}"


@dataclass(frozen=True, slots=True)
class ChildDeviceSpec:
    """A room or generator that should have a Heatprint child device."""

    suffix: str
    name: str
    area_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """A device already in the HA device registry."""

    device_id: str
    identifier_value: str
    area_id: str | None
    name_by_user: str | None


@dataclass(frozen=True, slots=True)
class DeviceAlignment:
    """One safe device-registry update (empty area and/or legacy auto-name)."""

    device_id: str
    area_id: str | None = None
    clear_name_by_user: bool = False


def plan_child_device_alignment(
    *,
    entry_id: str,
    site_name: str,
    children: Sequence[ChildDeviceSpec],
    devices: Sequence[DeviceSnapshot],
) -> tuple[DeviceAlignment, ...]:
    """Diff child devices against the registry. Never overwrites a set area."""
    by_ident = {device.identifier_value: device for device in devices}
    ops: list[DeviceAlignment] = []
    for child in children:
        device = by_ident.get(device_identifier(entry_id, child.suffix))
        if device is None:
            continue
        new_area = child.area_id if child.area_id and not device.area_id else None
        clear_name = is_legacy_auto_device_name(device.name_by_user, site_name, child.name)
        if new_area or clear_name:
            ops.append(
                DeviceAlignment(
                    device_id=device.device_id,
                    area_id=new_area,
                    clear_name_by_user=clear_name,
                )
            )
    return tuple(ops)


def suggested_area_name(hass: Any, area_id: str | None, fallback: str | None = None) -> str | None:
    """Return the HA area name for ``suggested_area``, or ``fallback``."""
    if not area_id:
        return None
    try:
        from homeassistant.helpers import area_registry as ar
    except ImportError:
        return fallback
    area = ar.async_get(hass).async_get_area(area_id)
    if area is not None and getattr(area, "name", None):
        return str(area.name)
    return fallback


def _snapshots_from_hass(hass: Any, entry_id: str) -> list[DeviceSnapshot]:
    """Read this config entry's devices into snapshots."""
    from homeassistant.helpers import device_registry as dr

    device_reg = dr.async_get(hass)
    snapshots: list[DeviceSnapshot] = []
    for device in dr.async_entries_for_config_entry(device_reg, entry_id):
        for domain, value in device.identifiers:
            if domain == DOMAIN:
                snapshots.append(
                    DeviceSnapshot(
                        device_id=device.id,
                        identifier_value=value,
                        area_id=device.area_id,
                        name_by_user=device.name_by_user,
                    )
                )
    return snapshots


def apply_device_alignment(hass: Any, plan: Iterable[DeviceAlignment]) -> int:
    """Apply alignment ops. Returns how many devices were updated."""
    from homeassistant.helpers import device_registry as dr

    device_reg = dr.async_get(hass)
    updated = 0
    for op in plan:
        kwargs: dict[str, Any] = {}
        if op.area_id:
            kwargs["area_id"] = op.area_id
        if op.clear_name_by_user:
            kwargs["name_by_user"] = None
        if not kwargs:
            continue
        device_reg.async_update_device(op.device_id, **kwargs)
        updated += 1
        if op.area_id:
            _LOGGER.info(
                "Heatprint assigned device %s to HA area %s",
                op.device_id,
                op.area_id,
            )
        if op.clear_name_by_user:
            _LOGGER.info(
                "Heatprint cleared legacy site-prefixed name on device %s",
                op.device_id,
            )
    return updated


def align_heatprint_devices(hass: Any, coordinator: Any) -> int:
    """Best-effort area fill and legacy-name cleanup after platforms are set up."""
    entry = coordinator.entry
    children = [
        ChildDeviceSpec(room.room_id, room.name, room.area_id) for room in coordinator.rooms
    ]
    children.extend(
        ChildDeviceSpec(generator.generator_id, generator.name, None)
        for generator in coordinator.generators
    )
    plan = plan_child_device_alignment(
        entry_id=entry.entry_id,
        site_name=coordinator.site_name,
        children=children,
        devices=_snapshots_from_hass(hass, entry.entry_id),
    )
    if not plan:
        return 0
    return apply_device_alignment(hass, plan)
