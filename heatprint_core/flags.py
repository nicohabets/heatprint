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


def is_usable(flags: Iterable[Flag]) -> bool:
    """Return True when none of the exclusion flags is present."""
    return not (set(flags) & EXCLUSION_FLAGS)


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
