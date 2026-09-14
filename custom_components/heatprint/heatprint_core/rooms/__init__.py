"""Per-room heat allocation and room energy-signature fits (METHODS section 12)."""

from .allocation import (
    RoomDayInput,
    allocate_day,
    allocate_period,
    daily_demand_integral,
    indicative_ua_w_per_k,
    room_weight,
)
from .signature import apply_room_not_fitted, fit_room_signature

__all__ = [
    "RoomDayInput",
    "allocate_day",
    "allocate_period",
    "apply_room_not_fitted",
    "daily_demand_integral",
    "fit_room_signature",
    "indicative_ua_w_per_k",
    "room_weight",
]
