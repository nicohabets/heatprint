"""Data quality flags (METHODS section 10).

Flags are string enums so that they serialise naturally to JSON and to sensor
attributes. The definition order is also the bit order of the compact bitmask used
by the JSON store (DATA_MODEL section 2.2).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Flag(StrEnum):
    """Per-day data quality flags. See METHODS section 10 for the effect of each flag."""

    #: No weather data for the day: excluded from fits and k calculations.
    WEATHER_MISSING = "weather_missing"
    #: Wind, radiation or the previous day is missing: methods fall back, allowed in fits.
    WEATHER_PARTIAL = "weather_partial"
    #: Provisional weather data that will be overwritten later.
    WEATHER_PROVISIONAL = "weather_provisional"
    #: No energy data for the day: excluded.
    ENERGY_MISSING = "energy_missing"
    #: Incomplete coverage of the day (first or last reading inside the day): excluded.
    PARTIAL_DAY = "partial_day"
    #: Consumption interpolated over a gap of more than 3 days: allowed, weight 1.
    INTERPOLATED = "interpolated"
    #: A meter reset happened on this day: excluded.
    METER_RESET = "meter_reset"
    #: Heat pump heat estimated from electricity and SCOP: allowed, labelled.
    HEAT_ESTIMATED = "heat_estimated"
    #: No house fit available: the house method uses its fallback.
    HOUSE_NOT_FITTED = "house_not_fitted"
    #: Residual larger than 4 x rmse in the signature fit: excluded after the refit.
    OUTLIER = "outlier"
    #: Imported from CSV: informational.
    IMPORTED = "imported"
    #: DHW baseline could not be estimated (fewer than 30 summer/rolling days):
    #: all heat of that generator counts as space heating. Informational, allowed
    #: in fits.
    DHW_BASELINE_MISSING = "dhw_baseline_missing"
    #: No demand-entity data for that room on that day (METHODS section 12.7).
    ROOM_DEMAND_MISSING = "room_demand_missing"
    #: Demand integral read from raw history, not long-term statistics.
    ROOM_DEMAND_FROM_HISTORY = "room_demand_from_history"
    #: Room weight defaulted (no rated output, or floor-area default used).
    ROOM_WEIGHT_ASSUMED = "room_weight_assumed"
    #: Fewer than 30 qualifying days for a room energy-signature fit.
    ROOM_NOT_FITTED = "room_not_fitted"
    #: No room temperature available for the indicative UA estimate.
    ROOM_TEMPERATURE_MISSING = "room_temperature_missing"


#: Flags that exclude a day from the signature fit and from k calculations
#: (METHODS section 7 step 1 and section 10).
EXCLUSION_FLAGS: frozenset[Flag] = frozenset(
    {
        Flag.WEATHER_MISSING,
        Flag.ENERGY_MISSING,
        Flag.PARTIAL_DAY,
        Flag.METER_RESET,
        Flag.OUTLIER,
    }
)


#: Flags that exclude a room-day from allocation and from the room fit
#: (METHODS section 12.7). Site-level ``is_usable`` is unchanged.
ROOM_EXCLUSION_FLAGS: frozenset[Flag] = frozenset({Flag.ROOM_DEMAND_MISSING})


def is_usable(flags: Iterable[Flag]) -> bool:
    """Return True when none of the exclusion flags is present."""
    return not (set(flags) & EXCLUSION_FLAGS)


def is_room_usable(flags: Iterable[Flag]) -> bool:
    """Return True when the room-day can be allocated and used in a room fit."""
    return not (set(flags) & ROOM_EXCLUSION_FLAGS)


def flags_to_bitmask(flags: Iterable[Flag]) -> int:
    """Encode a set of flags as an integer bitmask (bit i = i-th flag in definition order)."""
    order = list(Flag)
    mask = 0
    for flag in flags:
        mask |= 1 << order.index(Flag(flag))
    return mask


def flags_from_bitmask(mask: int) -> set[Flag]:
    """Decode an integer bitmask produced by :func:`flags_to_bitmask`."""
    return {flag for index, flag in enumerate(Flag) if mask & (1 << index)}


def parse_flags(values: Iterable[str | Flag]) -> set[Flag]:
    """Convert an iterable of flag names or values (case-insensitive) into a set of flags."""
    result: set[Flag] = set()
    for value in values:
        if isinstance(value, Flag):
            result.add(value)
            continue
        text = str(value).strip().lower()
        result.add(Flag(text))
    return result
