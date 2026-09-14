"""Parse recorder/history samples for room demand and temperature.

Home Assistant-free so METHODS §12 binary/climate fallbacks can be unit-tested.
Climate entities store HVAC mode as state and heating as ``hvac_action``;
current temperature lives on ``current_temperature``, not in the state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HEATING_STATES = frozenset({"on", "heat", "heating", "1", "true", "yes"})
IDLE_STATES = frozenset({"off", "idle", "false", "no", "0", "fan", "dry", "defrosting"})
UNAVAILABLE_STATES = frozenset({"unknown", "unavailable", ""})


def _text(value: Any) -> str:
    """Return a stripped lower-case string for a sample field."""
    if value is None:
        return ""
    return str(value).strip().lower()


def heating_from_sample(state: Any, attributes: Mapping[str, Any] | None = None) -> float | None:
    """Return 1.0 when the sample is heating, 0.0 when idle, else a numeric value.

    Prefer ``hvac_action`` when present so a climate entity in mode ``heat``
    that is currently ``idle`` is not counted as demand (METHODS §12.1).
    """
    attrs = attributes or {}
    action = _text(attrs.get("hvac_action"))
    if action:
        if action in HEATING_STATES:
            return 1.0
        if action in IDLE_STATES:
            return 0.0
    text = _text(state)
    if text in UNAVAILABLE_STATES:
        return None
    if text in HEATING_STATES:
        return 1.0
    if text in IDLE_STATES:
        return 0.0
    try:
        return float(state)
    except (TypeError, ValueError):
        return None


def temperature_from_sample(
    state: Any, attributes: Mapping[str, Any] | None = None
) -> float | None:
    """Return a room temperature from a climate/sensor sample."""
    attrs = attributes or {}
    current = attrs.get("current_temperature")
    if current is not None:
        try:
            return float(current)
        except (TypeError, ValueError):
            pass
    text = _text(state)
    if text in UNAVAILABLE_STATES or text in HEATING_STATES or text in IDLE_STATES:
        return None
    try:
        return float(state)
    except (TypeError, ValueError):
        return None


def numeric_from_sample(state: Any, attributes: Mapping[str, Any] | None = None) -> float | None:
    """Auto value: number if possible, else heating from ``hvac_action``/state."""
    text = _text(state)
    if text in UNAVAILABLE_STATES:
        heating = heating_from_sample(state, attributes)
        return heating
    try:
        return float(state)
    except (TypeError, ValueError):
        return heating_from_sample(state, attributes)


def value_from_sample(
    state: Any,
    attributes: Mapping[str, Any] | None = None,
    *,
    mode: str = "auto",
) -> float | None:
    """Dispatch a history sample to heating, temperature or auto numeric."""
    if mode == "heating":
        return heating_from_sample(state, attributes)
    if mode == "temperature":
        return temperature_from_sample(state, attributes)
    return numeric_from_sample(state, attributes)


def demand_requires_history(demand_entity: str | None, demand_kind: str) -> bool:
    """True when statistics would be the climate temperature, not demand.

    A climate entity's long-term ``mean`` is room temperature. Binary demand
    from ``hvac_action`` must come from raw history (METHODS §12.1 / §12.6).
    """
    return bool(demand_kind == "binary" and demand_entity and demand_entity.startswith("climate."))
