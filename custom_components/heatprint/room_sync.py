"""Idempotent create/update of room subentries from discovered HA areas.

The plan is Home Assistant-free. Applying it talks to ``config_entries``.
User overrides (``rated_output_w``, ``emitter_kind``, ``floor_area_m2``,
``volume_m3``, ``enabled``, ``price_entity``, custom ``name``) are kept on
update. Entity links (demand, kind, temperature, ``area_id``) are refreshed
when discovery finds a better or moved entity.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

try:
    from .room_discovery import DiscoveredRoom, DiscoveryResult, discover_rooms_from_hass
except ImportError:  # pytest pythonpath: custom_components/heatprint
    from room_discovery import DiscoveredRoom, DiscoveryResult, discover_rooms_from_hass

# Keep keys in lockstep with const.py (this module must stay HA-free).
CONF_AREA_ID = "area_id"
CONF_DEMAND_ENTITY = "demand_entity"
CONF_DEMAND_KIND = "demand_kind"
CONF_EMITTER_KIND = "emitter_kind"
CONF_ENABLED = "enabled"
CONF_FLOOR_AREA_M2 = "floor_area_m2"
CONF_NAME = "name"
CONF_PRICE_ENTITY = "price_entity"
CONF_RATED_OUTPUT_W = "rated_output_w"
CONF_ROOM_ID = "room_id"
CONF_ROOM_TEMPERATURE_ENTITY = "temperature_entity"
CONF_ROOMS_AUTO_SYNC = "auto_sync"
CONF_ROOMS_EXCLUDE_AREAS = "exclude_area_ids"
CONF_VOLUME_M3 = "volume_m3"
DEFAULT_ROOMS_AUTO_SYNC = True
DOMAIN = "heatprint"
EMITTER_KIND_RADIATOR = "radiator"
OPT_ROOMS = "rooms"
SUBENTRY_TYPE_ROOM = "room"

_LOGGER = logging.getLogger(__name__)

AREA_UNIQUE_PREFIX = "area:"


def slugify_room(name: str) -> str:
    """Return a statistic-safe room id from an area name (NL-safe ASCII)."""
    normalized = unicodedata.normalize("NFKD", name or "")
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    return slug or "room"


def unique_slug(name: str, existing: set[str], fallback: str = "room") -> str:
    """Return a slug derived from ``name`` that is not in ``existing``."""
    base = slugify_room(name) or fallback
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def area_unique_id(area_id: str) -> str:
    """Stable subentry unique_id for an auto-discovered area."""
    return f"{AREA_UNIQUE_PREFIX}{area_id}"


@dataclass(frozen=True, slots=True)
class ExistingRoom:
    """A room already stored as a subentry (or an equivalent list)."""

    room_id: str
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
    unique_id: str | None = None
    subentry_id: str | None = None


@dataclass(frozen=True, slots=True)
class RoomSyncOp:
    """One create or update against the stored room list."""

    action: Literal["create", "update"]
    room: dict[str, Any]
    title: str
    unique_id: str
    subentry_id: str | None = None


@dataclass(frozen=True, slots=True)
class RoomSyncPlan:
    """Ops plus the discovery snapshot used to build them."""

    ops: tuple[RoomSyncOp, ...]
    discovery: DiscoveryResult

    @property
    def changed(self) -> bool:
        """True when at least one subentry would be created or updated."""
        return bool(self.ops)

    def summary(self) -> str:
        """Short created/updated counts for options placeholders."""
        created = sum(1 for op in self.ops if op.action == "create")
        updated = sum(1 for op in self.ops if op.action == "update")
        return f"{created} created, {updated} updated"


def existing_room_from_data(
    data: Mapping[str, Any],
    *,
    title: str | None = None,
    unique_id: str | None = None,
    subentry_id: str | None = None,
) -> ExistingRoom:
    """Build an :class:`ExistingRoom` from stored subentry data."""
    rated = data.get(CONF_RATED_OUTPUT_W)
    area = data.get(CONF_FLOOR_AREA_M2)
    volume = data.get(CONF_VOLUME_M3)
    return ExistingRoom(
        room_id=str(data.get(CONF_ROOM_ID) or slugify_room(str(data.get(CONF_NAME) or "room"))),
        name=str(data.get(CONF_NAME) or title or ""),
        area_id=data.get(CONF_AREA_ID),
        demand_entity=data.get(CONF_DEMAND_ENTITY),
        demand_kind=str(data.get(CONF_DEMAND_KIND) or "percentage"),
        temperature_entity=data.get(CONF_ROOM_TEMPERATURE_ENTITY),
        emitter_kind=str(data.get(CONF_EMITTER_KIND) or EMITTER_KIND_RADIATOR),
        rated_output_w=float(rated) if rated is not None else None,
        floor_area_m2=float(area) if area is not None else None,
        volume_m3=float(volume) if volume is not None else None,
        price_entity=data.get(CONF_PRICE_ENTITY),
        enabled=bool(data.get(CONF_ENABLED, True)),
        unique_id=unique_id,
        subentry_id=subentry_id,
    )


def _match_existing(
    discovered: DiscoveredRoom, existing: Sequence[ExistingRoom]
) -> ExistingRoom | None:
    """Return the stored room for this area, if any."""
    wanted = area_unique_id(discovered.area_id)
    for room in existing:
        if room.unique_id in {wanted, discovered.area_id}:
            return room
        if room.area_id and room.area_id == discovered.area_id:
            return room
    return None


def _room_data_from_discovered(
    discovered: DiscoveredRoom,
    *,
    room_id: str,
    existing: ExistingRoom | None,
) -> dict[str, Any]:
    """Build stored subentry data, preserving user overrides on update."""
    if existing is None:
        return {
            CONF_ROOM_ID: room_id,
            CONF_NAME: discovered.name,
            CONF_AREA_ID: discovered.area_id,
            CONF_DEMAND_ENTITY: discovered.demand_entity,
            CONF_DEMAND_KIND: discovered.demand_kind,
            CONF_ROOM_TEMPERATURE_ENTITY: discovered.temperature_entity,
            CONF_EMITTER_KIND: discovered.emitter_kind,
            CONF_ENABLED: True,
        }
    data: dict[str, Any] = {
        CONF_ROOM_ID: existing.room_id,
        CONF_NAME: existing.name or discovered.name,
        CONF_AREA_ID: discovered.area_id,
        CONF_DEMAND_ENTITY: discovered.demand_entity,
        CONF_DEMAND_KIND: discovered.demand_kind,
        CONF_EMITTER_KIND: existing.emitter_kind or discovered.emitter_kind,
        CONF_ENABLED: existing.enabled,
    }
    if discovered.temperature_entity:
        data[CONF_ROOM_TEMPERATURE_ENTITY] = discovered.temperature_entity
    elif existing.temperature_entity:
        data[CONF_ROOM_TEMPERATURE_ENTITY] = existing.temperature_entity
    if existing.rated_output_w is not None:
        data[CONF_RATED_OUTPUT_W] = existing.rated_output_w
    if existing.floor_area_m2 is not None:
        data[CONF_FLOOR_AREA_M2] = existing.floor_area_m2
    if existing.volume_m3 is not None:
        data[CONF_VOLUME_M3] = existing.volume_m3
    if existing.price_entity:
        data[CONF_PRICE_ENTITY] = existing.price_entity
    return data


def _links_changed(existing: ExistingRoom, discovered: DiscoveredRoom) -> bool:
    """True when demand / temperature / area links should be rewritten."""
    temperature = discovered.temperature_entity or existing.temperature_entity
    return (
        existing.demand_entity != discovered.demand_entity
        or existing.demand_kind != discovered.demand_kind
        or existing.temperature_entity != temperature
        or existing.area_id != discovered.area_id
    )


def plan_room_sync(
    existing: Sequence[ExistingRoom],
    discovery: DiscoveryResult,
    *,
    slugify: Callable[[str], str] = slugify_room,
) -> RoomSyncPlan:
    """Diff stored rooms against discovery. Does not delete missing areas."""
    taken = {room.room_id for room in existing}
    ops: list[RoomSyncOp] = []
    for discovered in discovery.rooms:
        match = _match_existing(discovered, existing)
        unique_id = area_unique_id(discovered.area_id)
        if match is None:
            room_id = unique_slug(discovered.name, taken, slugify(discovered.name) or "room")
            taken.add(room_id)
            data = _room_data_from_discovered(discovered, room_id=room_id, existing=None)
            ops.append(
                RoomSyncOp(
                    action="create",
                    room=data,
                    title=discovered.name,
                    unique_id=unique_id,
                )
            )
            continue
        if not _links_changed(match, discovered):
            continue
        data = _room_data_from_discovered(discovered, room_id=match.room_id, existing=match)
        ops.append(
            RoomSyncOp(
                action="update",
                room=data,
                title=match.name or discovered.name,
                unique_id=match.unique_id or unique_id,
                subentry_id=match.subentry_id,
            )
        )
    return RoomSyncPlan(ops=tuple(ops), discovery=discovery)


def existing_rooms_from_entry(entry: Any) -> list[ExistingRoom]:
    """Read ``room`` subentries from a config entry."""
    rooms: list[ExistingRoom] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_ROOM:
            continue
        rooms.append(
            existing_room_from_data(
                subentry.data,
                title=subentry.title,
                unique_id=getattr(subentry, "unique_id", None),
                subentry_id=getattr(subentry, "subentry_id", None),
            )
        )
    return rooms


def exclude_area_ids_from_options(options: Mapping[str, Any] | None) -> list[str]:
    """Return the configured exclude-area list."""
    rooms = dict((options or {}).get(OPT_ROOMS) or {})
    raw = rooms.get(CONF_ROOMS_EXCLUDE_AREAS) or []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw if item]


def auto_sync_enabled(options: Mapping[str, Any] | None) -> bool:
    """Return whether rooms should be synced from HA areas (default on)."""
    rooms = dict((options or {}).get(OPT_ROOMS) or {})
    return bool(rooms.get(CONF_ROOMS_AUTO_SYNC, DEFAULT_ROOMS_AUTO_SYNC))


def plan_from_entry(entry: Any, discovery: DiscoveryResult) -> RoomSyncPlan:
    """Build a sync plan for a live config entry."""
    return plan_room_sync(existing_rooms_from_entry(entry), discovery)


def _make_config_subentry(data: Mapping[str, Any], title: str, unique_id: str) -> Any:
    """Construct a ``ConfigSubentry`` across slightly different HA signatures."""
    from homeassistant.config_entries import ConfigSubentry

    kwargs: dict[str, Any] = {
        "data": dict(data),
        "subentry_type": SUBENTRY_TYPE_ROOM,
        "title": title,
        "unique_id": unique_id,
    }
    try:
        return ConfigSubentry(**kwargs)
    except TypeError:
        from homeassistant.util import ulid as ulid_util

        return ConfigSubentry(subentry_id=ulid_util.ulid_now(), **kwargs)


def apply_room_sync(hass: Any, entry: Any, plan: RoomSyncPlan) -> RoomSyncPlan:
    """Create or update room subentries. Returns the plan that was applied."""
    for op in plan.ops:
        if op.action == "create":
            hass.config_entries.async_add_subentry(
                entry, _make_config_subentry(op.room, op.title, op.unique_id)
            )
            _LOGGER.info(
                "Heatprint added room %s from HA area %s",
                op.room.get(CONF_NAME),
                op.room.get(CONF_AREA_ID),
            )
            continue
        subentry = None
        if op.subentry_id:
            subentry = entry.subentries.get(op.subentry_id)
        if subentry is None:
            for candidate in entry.subentries.values():
                if candidate.subentry_type != SUBENTRY_TYPE_ROOM:
                    continue
                if getattr(candidate, "unique_id", None) == op.unique_id:
                    subentry = candidate
                    break
                if candidate.data.get(CONF_AREA_ID) == op.room.get(CONF_AREA_ID):
                    subentry = candidate
                    break
        if subentry is None:
            hass.config_entries.async_add_subentry(
                entry, _make_config_subentry(op.room, op.title, op.unique_id)
            )
            continue
        hass.config_entries.async_update_subentry(entry, subentry, data=op.room, title=op.title)
        _LOGGER.info(
            "Heatprint updated room %s entity links from HA area %s",
            op.room.get(CONF_NAME),
            op.room.get(CONF_AREA_ID),
        )
    return plan


def sync_rooms_from_hass(hass: Any, entry: Any) -> RoomSyncPlan:
    """Discover HA areas and apply an idempotent room-subentry sync."""
    exclude = exclude_area_ids_from_options(entry.options)
    discovery = discover_rooms_from_hass(hass, exclude_area_ids=exclude)
    plan = plan_from_entry(entry, discovery)
    if plan.changed:
        apply_room_sync(hass, entry, plan)
    return plan


def _empty_plan(entry: Any) -> RoomSyncPlan:
    """Return a no-op plan for the current subentries."""
    return plan_from_entry(entry, DiscoveryResult(rooms=(), skipped=()))


def sync_rooms_if_auto(hass: Any, entry: Any) -> RoomSyncPlan:
    """Sync rooms when the auto-sync option is on (default)."""
    key = f"{DOMAIN}_room_sync_{getattr(entry, 'entry_id', id(entry))}"
    bag = hass.data.setdefault(DOMAIN, {})
    if bag.get(key):
        return _empty_plan(entry)
    if not auto_sync_enabled(entry.options):
        return _empty_plan(entry)
    bag[key] = True
    try:
        return sync_rooms_from_hass(hass, entry)
    finally:
        bag[key] = False


def discovered_to_subentry_payloads(
    rooms: Iterable[DiscoveredRoom],
    *,
    existing_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Turn first-run discovery into ``ConfigSubentryData``-ready room dicts."""
    taken = set(existing_ids or ())
    payloads: list[dict[str, Any]] = []
    for discovered in rooms:
        room_id = unique_slug(discovered.name, taken)
        taken.add(room_id)
        payloads.append(
            {
                "data": _room_data_from_discovered(discovered, room_id=room_id, existing=None),
                "title": discovered.name,
                "unique_id": area_unique_id(discovered.area_id),
            }
        )
    return payloads
