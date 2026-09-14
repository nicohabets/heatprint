"""Discover heated Home Assistant areas as Heatprint rooms (METHODS §12.6).

Home Assistant-free so the heuristics can be unit-tested with fixture
registries. The adapter :func:`discover_rooms_from_hass` reads the live
area / entity / device registries.

Heuristics (include an area only when it looks like a heated room):

1. Skip areas on the exclude list.
2. Skip areas with a Tado-style ``select.*heating_circuit`` (or a climate
   attribute) whose state is ``no_heating_circuit`` — Nico's Keldertrap /
   Overloop / Sauna / Toilet zones.
3. Skip areas with no ``climate`` entity and no heating-demand / valve
   sensor (empty rooms, hallways with lights only).
4. Demand entity, in order: percentage heating-power sensor in the area
   (Tado ``*_verwarming``, ``heating_power``, ``pi_heating_demand``, …);
   else a valve-position sensor; else the area's ``climate`` entity as
   ``binary`` demand from ``hvac_action``.
5. Temperature: the area's ``climate`` entity (state / ``current_temperature``).
6. Emitter kind is a name heuristic only (vloerverwarming → underfloor);
   user overrides are never inferred as rated output or floor area.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Keep these in lockstep with const.py (this module must stay HA-free).
DEMAND_KIND_BINARY = "binary"
DEMAND_KIND_PERCENTAGE = "percentage"
DEMAND_KIND_VALVE = "valve_position"
EMITTER_KIND_ELECTRIC = "electric"
EMITTER_KIND_RADIATOR = "radiator"
EMITTER_KIND_UNDERFLOOR = "underfloor"

NO_HEATING_CIRCUIT = "no_heating_circuit"

# Tokens matched against ``name entity_id`` (lower-case). Dutch Tado names
# use "verwarming" for the zone heating-power percentage sensor.
PERCENTAGE_TOKENS: tuple[str, ...] = (
    "verwarming",
    "verwarmingsvraag",
    "heating_power",
    "heating-power",
    "heating power",
    "heat_demand",
    "heat-demand",
    "heat demand",
    "heating_demand",
    "heating-demand",
    "heating demand",
    "pi_heating_demand",
    "pi-heating-demand",
)
VALVE_TOKENS: tuple[str, ...] = (
    "valve_position",
    "valve-position",
    "valve position",
    "valve_opening",
    "klepstand",
    "valve",
)
PERCENTAGE_SKIP_TOKENS: tuple[str, ...] = (
    "humidity",
    "luchtvochtigheid",
    "battery",
    "batterij",
    "brightness",
    "helderheid",
)
UNDERFLOOR_TOKENS: tuple[str, ...] = (
    "underfloor",
    "vloerverwarming",
    "floor_heating",
    "floor-heating",
    "floor heating",
)
ELECTRIC_TOKENS: tuple[str, ...] = ("electric floor", "elektrische vloerverwarming")
HEATING_CIRCUIT_TOKENS: tuple[str, ...] = ("heating_circuit", "heating-circuit", "heating circuit")

SKIP_EXCLUDED = "excluded"
SKIP_NO_HEATING_CIRCUIT = "no_heating_circuit"
SKIP_NO_SIGNAL = "no_climate_or_demand"


@dataclass(frozen=True, slots=True)
class RegistryArea:
    """One Home Assistant area."""

    area_id: str
    name: str


@dataclass(frozen=True, slots=True)
class RegistryEntity:
    """One entity with the area it belongs to (own or via device)."""

    entity_id: str
    area_id: str | None
    name: str
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    state: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)
    device_id: str | None = None

    @property
    def domain(self) -> str:
        """Return the HA domain (the part before the first dot)."""
        return self.entity_id.split(".", 1)[0]

    @property
    def haystack(self) -> str:
        """Lower-case name + entity_id for token matching."""
        return f"{self.name} {self.entity_id}".lower()


@dataclass(frozen=True, slots=True)
class DiscoveredRoom:
    """A heated area with the entities Heatprint should use."""

    area_id: str
    name: str
    demand_entity: str
    demand_kind: str
    temperature_entity: str | None
    climate_entity: str | None
    emitter_kind: str


@dataclass(frozen=True, slots=True)
class SkippedArea:
    """An area that was not turned into a room, with the heuristic reason."""

    area_id: str
    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Included rooms plus skipped areas (counts for confirm; detail for sync/logs)."""

    rooms: tuple[DiscoveredRoom, ...]
    skipped: tuple[SkippedArea, ...]

    def confirm_counts(self) -> dict[str, str]:
        """Short counts for the first-run confirm placeholders."""
        return {
            "room_count": str(len(self.rooms)),
            "skipped_count": str(len(self.skipped)),
        }

    def room_summary(self) -> str:
        """Human-readable included-room list for logs and Sync rooms."""
        if not self.rooms:
            return "—"
        parts: list[str] = []
        for room in self.rooms:
            extra = room.demand_kind
            if room.demand_entity:
                extra = f"{room.demand_kind} {room.demand_entity}"
            parts.append(f"{room.name} ({extra})")
        return "; ".join(parts)

    def skipped_summary(self) -> str:
        """Human-readable skipped-area list for logs and Sync rooms."""
        if not self.skipped:
            return "—"
        return "; ".join(f"{item.name} ({item.reason})" for item in self.skipped)


def _haystack(entity: RegistryEntity) -> str:
    """Return the token haystack of an entity."""
    return entity.haystack


def _is_percentage_unit(unit: str | None) -> bool:
    """True when the unit looks like a 0-100 heating-power percentage."""
    if not unit:
        return False
    return unit.strip() in {"%", "percent", "PERCENTAGE"}


def _looks_like_percentage_demand(entity: RegistryEntity) -> bool:
    """True for a Tado-style heating-power (or PI demand) percentage sensor."""
    if entity.domain != "sensor":
        return False
    haystack = _haystack(entity)
    if any(token in haystack for token in PERCENTAGE_SKIP_TOKENS):
        return False
    if not any(token in haystack for token in PERCENTAGE_TOKENS):
        return False
    if entity.device_class in {"humidity", "battery", "illuminance"}:
        return False
    # Allow unitless PI demand (0-255 / 0-100) when the name is explicit.
    return not (
        entity.unit
        and not _is_percentage_unit(entity.unit)
        and entity.unit not in {"", None}
        and "pi_heating_demand" not in haystack
        and "pi-heating-demand" not in haystack
    )


def _looks_like_valve(entity: RegistryEntity) -> bool:
    """True for a TRV valve-position sensor."""
    if entity.domain != "sensor":
        return False
    haystack = _haystack(entity)
    if any(token in haystack for token in PERCENTAGE_SKIP_TOKENS):
        return False
    return any(token in haystack for token in VALVE_TOKENS)


def _looks_like_heating_circuit(entity: RegistryEntity) -> bool:
    """True for a Tado/tado_ce heating-circuit select (or similar)."""
    haystack = _haystack(entity)
    if not any(token in haystack for token in HEATING_CIRCUIT_TOKENS):
        return False
    return entity.domain in {"select", "sensor", "input_select"}


def _area_has_no_heating_circuit(entities: Iterable[RegistryEntity]) -> bool:
    """True when a zone reports ``no_heating_circuit`` (METHODS §12.6)."""
    for entity in entities:
        state = (entity.state or "").strip().lower()
        if _looks_like_heating_circuit(entity) and state == NO_HEATING_CIRCUIT:
            return True
        attrs = entity.attributes or {}
        for key in ("heating_circuit", "selected_heating_circuit", "heating_type"):
            if str(attrs.get(key, "")).strip().lower() == NO_HEATING_CIRCUIT:
                return True
    return False


def _pick_climate(entities: list[RegistryEntity]) -> RegistryEntity | None:
    """Return the first climate entity in the area (stable by entity_id)."""
    climates = [entity for entity in entities if entity.domain == "climate"]
    climates.sort(key=lambda item: item.entity_id)
    return climates[0] if climates else None


def _pick_percentage(entities: list[RegistryEntity]) -> RegistryEntity | None:
    """Prefer a % heating-power sensor; stable by entity_id."""
    matches = [entity for entity in entities if _looks_like_percentage_demand(entity)]
    matches.sort(key=lambda item: item.entity_id)
    return matches[0] if matches else None


def _pick_valve(entities: list[RegistryEntity]) -> RegistryEntity | None:
    """Prefer a valve-position sensor that is not also a heating-power %."""
    matches = [
        entity
        for entity in entities
        if _looks_like_valve(entity) and not _looks_like_percentage_demand(entity)
    ]
    matches.sort(key=lambda item: item.entity_id)
    return matches[0] if matches else None


def guess_emitter_kind(*names: str | None) -> str:
    """Guess emitter kind from area/entity names; default radiator."""
    haystack = " ".join(name for name in names if name).lower()
    if any(token in haystack for token in UNDERFLOOR_TOKENS):
        return EMITTER_KIND_UNDERFLOOR
    if any(token in haystack for token in ELECTRIC_TOKENS):
        return EMITTER_KIND_ELECTRIC
    return EMITTER_KIND_RADIATOR


def discover_rooms(
    areas: Iterable[RegistryArea],
    entities: Iterable[RegistryEntity],
    *,
    exclude_area_ids: Collection[str] = (),
) -> DiscoveryResult:
    """Return heated rooms and skipped areas from a registry snapshot."""
    excluded = {area_id for area_id in exclude_area_ids if area_id}
    by_area: dict[str, list[RegistryEntity]] = {}
    for entity in entities:
        if not entity.area_id:
            continue
        by_area.setdefault(entity.area_id, []).append(entity)

    rooms: list[DiscoveredRoom] = []
    skipped: list[SkippedArea] = []
    for area in sorted(areas, key=lambda item: (item.name.lower(), item.area_id)):
        members = by_area.get(area.area_id, [])
        if area.area_id in excluded:
            skipped.append(SkippedArea(area.area_id, area.name, SKIP_EXCLUDED))
            continue
        if _area_has_no_heating_circuit(members):
            skipped.append(SkippedArea(area.area_id, area.name, SKIP_NO_HEATING_CIRCUIT))
            continue
        climate = _pick_climate(members)
        percentage = _pick_percentage(members)
        valve = _pick_valve(members)
        if percentage is not None:
            demand_entity, demand_kind = percentage.entity_id, DEMAND_KIND_PERCENTAGE
        elif valve is not None:
            demand_entity, demand_kind = valve.entity_id, DEMAND_KIND_VALVE
        elif climate is not None:
            demand_entity, demand_kind = climate.entity_id, DEMAND_KIND_BINARY
        else:
            skipped.append(SkippedArea(area.area_id, area.name, SKIP_NO_SIGNAL))
            continue
        temperature = climate.entity_id if climate is not None else None
        rooms.append(
            DiscoveredRoom(
                area_id=area.area_id,
                name=area.name,
                demand_entity=demand_entity,
                demand_kind=demand_kind,
                temperature_entity=temperature,
                climate_entity=temperature,
                emitter_kind=guess_emitter_kind(area.name, demand_entity, temperature),
            )
        )
    return DiscoveryResult(rooms=tuple(rooms), skipped=tuple(skipped))


def collect_registry_snapshot(hass: Any) -> tuple[list[RegistryArea], list[RegistryEntity]]:
    """Read HA area / entity / device registries into snapshot dataclasses.

    ``hass`` is typed as ``Any`` so tests and the core stay importable
    without Home Assistant installed.
    """
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    area_reg = ar.async_get(hass)
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    areas = [RegistryArea(area_id=area.id, name=area.name) for area in area_reg.async_list_areas()]
    entities: list[RegistryEntity] = []
    for entry in entity_reg.entities.values():
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = device_reg.async_get(entry.device_id)
            if device is not None:
                area_id = device.area_id
        state = hass.states.get(entry.entity_id) if hasattr(hass, "states") else None
        attrs = dict(getattr(state, "attributes", None) or {})
        unit = attrs.get("unit_of_measurement") or getattr(entry, "unit_of_measurement", None)
        device_class = (
            attrs.get("device_class")
            or getattr(entry, "device_class", None)
            or getattr(entry, "original_device_class", None)
        )
        name = (
            entry.name
            or getattr(entry, "original_name", None)
            or (getattr(state, "name", None) if state is not None else None)
            or entry.entity_id
        )
        entities.append(
            RegistryEntity(
                entity_id=entry.entity_id,
                area_id=area_id,
                name=str(name),
                unit=unit,
                device_class=device_class,
                state_class=attrs.get("state_class"),
                state=getattr(state, "state", None) if state is not None else None,
                attributes=attrs,
                device_id=entry.device_id,
            )
        )
    return areas, entities


def discover_rooms_from_hass(
    hass: Any, *, exclude_area_ids: Collection[str] = ()
) -> DiscoveryResult:
    """Discover heated rooms from the live Home Assistant registries."""
    areas, entities = collect_registry_snapshot(hass)
    return discover_rooms(areas, entities, exclude_area_ids=exclude_area_ids)
