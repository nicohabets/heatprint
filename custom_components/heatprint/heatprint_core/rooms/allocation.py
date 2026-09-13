"""Daily demand integral, room weights and allocation of site space heat (METHODS §12).

Allocation is additive on top of the site ``DailyRecord``: it never changes
``heat_space_kwh``. Metered rooms take their own kWh; the rest of the day's
space heat is split by ``w_r * D_r``. Leftover heat is the unallocated bucket.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from ..constants import DEFAULT_OUTPUT_W_PER_M2
from ..flags import Flag, is_room_usable
from ..models import DailyRecord, DailyRoomRecord, DemandKind, Room


@dataclass(frozen=True, slots=True)
class RoomDayInput:
    """Observed demand (and optional room temperature) of one room on one day.

    ``raw`` is the daily statistic used by :func:`daily_demand_integral`:
    mean percent (0-100) for ``percentage`` / ``valve_position``, on-fraction
    or hours-on for ``binary``, kWh for ``metered_energy``.
    """

    raw: float | None
    t_room_mean: float | None = None
    from_history: bool = False
    heating_hours: float | None = None


@dataclass(frozen=True, slots=True)
class DayAllocation:
    """Result of allocating one day's site space heat across rooms."""

    records: list[DailyRoomRecord]
    heat_unallocated_kwh: float
    cost_unallocated_eur: float | None = None


def daily_demand_integral(
    demand_kind: DemandKind,
    raw: float | None,
    *,
    heating_hours: float | None = None,
) -> float | None:
    """Convert a daily observation into ``D_r`` (METHODS section 12.1).

    For ``percentage`` / ``valve_position`` the native range is 0-100, so
    ``D_r = mean(%) / 100``. For ``binary``, ``D_r`` is the on-fraction of the
    day (hours / 24). For ``metered_energy`` the kWh *is* the heat and this
    function returns that kWh (not a 0-1 fraction).
    """
    if raw is None:
        return None
    value = float(raw)
    if demand_kind is DemandKind.METERED_ENERGY:
        return max(0.0, value)
    if demand_kind is DemandKind.BINARY:
        if heating_hours is not None:
            return max(0.0, min(1.0, float(heating_hours) / 24.0))
        # Daily mean of a 0/1 binary is already the on-fraction; a value above 1
        # is treated as hours-on (history fallback that counted hours).
        if value > 1.0:
            return max(0.0, min(1.0, value / 24.0))
        return max(0.0, min(1.0, value))
    # percentage / valve_position: 0-100 → 0-1 fraction of a fully-heated day.
    return max(0.0, min(1.0, value / 100.0))


def room_weight(
    room: Room, output_w_per_m2: Mapping[str, float] | None = None
) -> tuple[float, bool]:
    """Return ``(w_r, assumed)`` (METHODS section 12.2).

    ``assumed`` is True when the weight is not a user-supplied rated output
    (floor-area default or the unit weight of 1).
    """
    if room.rated_output_w is not None and room.rated_output_w > 0:
        return float(room.rated_output_w), False
    table = output_w_per_m2 or DEFAULT_OUTPUT_W_PER_M2
    if room.floor_area_m2 is not None and room.floor_area_m2 > 0:
        default = float(table.get(room.emitter_kind.value, table.get("other", 70.0)))
        return float(room.floor_area_m2) * default, True
    return 1.0, True


def indicative_ua_w_per_k(
    heat_kwh: float | None,
    t_room_mean: float | None,
    t_out: float | None,
    heating_hours: float | None,
) -> float | None:
    """Indicative UA (W/K) from one heating interval (METHODS section 12.4).

    ``heat / (T_room - t_out) / heating_hours * 1000``. Not used for cost or
    the season total; labelled as an estimate until a 30-day fit exists.
    """
    if (
        heat_kwh is None
        or t_room_mean is None
        or t_out is None
        or heating_hours is None
        or heating_hours <= 0
        or heat_kwh < 0
    ):
        return None
    delta = float(t_room_mean) - float(t_out)
    if delta <= 0.1:
        return None
    return float(heat_kwh) / delta / float(heating_hours) * 1000.0


def _heating_hours(room: Room, integral: float | None, heating_hours: float | None) -> float | None:
    if heating_hours is not None and heating_hours > 0:
        return float(heating_hours)
    if integral is None or room.is_metered:
        return None
    return float(integral) * 24.0


def _per_m2(heat_kwh: float | None, floor_area_m2: float | None) -> float | None:
    if heat_kwh is None or floor_area_m2 is None or floor_area_m2 <= 0:
        return None
    return float(heat_kwh) / float(floor_area_m2)


def allocate_day(
    rooms: Iterable[Room],
    inputs: Mapping[str, RoomDayInput],
    heat_space_kwh: float,
    *,
    t_mean: float | None = None,
    cost_space_eur: float | None = None,
    metered_prices: Mapping[str, float] | None = None,
    output_w_per_m2: Mapping[str, float] | None = None,
    day: date | None = None,
) -> DayAllocation:
    """Allocate one day's ``heat_space_kwh`` across enabled rooms (METHODS §12.3).

    ``cost_space_eur`` is optional (METHODS §12.5). When omitted, room cost
    stays ``None`` — site ``cost_eur`` is not written as a statistic yet.
    """
    enabled = [room for room in rooms if room.enabled]
    when = day or date.min
    records: list[DailyRoomRecord] = []
    heat_metered = 0.0
    cost_metered = 0.0
    has_metered_cost = False
    allocated: list[tuple[Room, DailyRoomRecord, float, float]] = []

    for room in enabled:
        observed = inputs.get(room.id, RoomDayInput(raw=None))
        flags: set[Flag] = set()
        if observed.from_history:
            flags.add(Flag.ROOM_DEMAND_FROM_HISTORY)
        weight, assumed = room_weight(room, output_w_per_m2)
        if assumed and not room.is_metered:
            flags.add(Flag.ROOM_WEIGHT_ASSUMED)
        if observed.t_room_mean is None:
            flags.add(Flag.ROOM_TEMPERATURE_MISSING)

        integral = daily_demand_integral(
            room.demand_kind, observed.raw, heating_hours=observed.heating_hours
        )
        if room.demand_entity is None or integral is None:
            flags.add(Flag.ROOM_DEMAND_MISSING)
            records.append(
                DailyRoomRecord(
                    date=when,
                    room_id=room.id,
                    demand_integral=integral,
                    t_room_mean=observed.t_room_mean,
                    flags=flags,
                )
            )
            continue

        if room.is_metered:
            heat = max(0.0, float(integral))
            heat_metered += heat
            price = (metered_prices or {}).get(room.id)
            cost: float | None = None
            if price is not None:
                cost = heat * float(price)
                cost_metered += cost
                has_metered_cost = True
            share = (heat / heat_space_kwh) if heat_space_kwh > 0 else None
            records.append(
                DailyRoomRecord(
                    date=when,
                    room_id=room.id,
                    demand_integral=heat,
                    t_room_mean=observed.t_room_mean,
                    share=share,
                    heat_room_kwh=heat,
                    cost_room_eur=cost,
                    heat_kwh_per_m2=_per_m2(heat, room.floor_area_m2),
                    flags=flags,
                )
            )
            continue

        record = DailyRoomRecord(
            date=when,
            room_id=room.id,
            demand_integral=integral,
            t_room_mean=observed.t_room_mean,
            flags=flags,
        )
        allocated.append((room, record, weight, integral))

    heat_to_allocate = max(0.0, float(heat_space_kwh) - heat_metered)
    cost_to_allocate: float | None = None
    if cost_space_eur is not None:
        cost_to_allocate = max(0.0, float(cost_space_eur) - (cost_metered if has_metered_cost else 0.0))

    denominator = sum(weight * integral for _room, _rec, weight, integral in allocated)
    heat_allocated = 0.0
    cost_allocated = 0.0
    finished: list[DailyRoomRecord] = []
    allocated_ids = {room.id for room, _rec, _w, _d in allocated}

    for room, record, weight, integral in allocated:
        if denominator <= 0:
            share = 0.0
            heat = 0.0
        else:
            share = (weight * integral) / denominator
            heat = share * heat_to_allocate
        heat_allocated += heat
        cost: float | None = None
        if cost_to_allocate is not None:
            cost = share * cost_to_allocate
            cost_allocated += cost
        finished.append(
            DailyRoomRecord(
                date=record.date,
                room_id=record.room_id,
                demand_integral=record.demand_integral,
                t_room_mean=record.t_room_mean,
                share=share,
                heat_room_kwh=heat,
                cost_room_eur=cost,
                heat_kwh_per_m2=_per_m2(heat, room.floor_area_m2),
                flags=set(record.flags),
            )
        )

    leftovers = [rec for rec in records if rec.room_id not in allocated_ids]
    heat_unallocated = max(0.0, heat_to_allocate - heat_allocated)
    cost_unallocated: float | None = None
    if cost_to_allocate is not None:
        cost_unallocated = max(0.0, cost_to_allocate - cost_allocated)
    _ = t_mean  # reserved for callers that attach indicative UA; unused here
    return DayAllocation(
        records=leftovers + finished,
        heat_unallocated_kwh=heat_unallocated,
        cost_unallocated_eur=cost_unallocated,
    )


def allocate_period(
    rooms: Iterable[Room],
    inputs_by_day: Mapping[date, Mapping[str, RoomDayInput]],
    site_records: Iterable[DailyRecord],
    *,
    output_w_per_m2: Mapping[str, float] | None = None,
    metered_prices: Mapping[date, Mapping[str, float]] | None = None,
) -> tuple[list[DailyRoomRecord], dict[date, float]]:
    """Allocate every day that has a site record. Returns records and unallocated kWh."""
    rooms = list(rooms)
    by_date = {record.date: record for record in site_records}
    all_records: list[DailyRoomRecord] = []
    unallocated: dict[date, float] = {}
    for day, site in sorted(by_date.items()):
        day_inputs = inputs_by_day.get(day, {})
        prices = (metered_prices or {}).get(day)
        result = allocate_day(
            rooms,
            day_inputs,
            site.heat_space_kwh,
            t_mean=site.t_mean,
            cost_space_eur=site.cost_eur,
            metered_prices=prices,
            output_w_per_m2=output_w_per_m2,
            day=day,
        )
        all_records.extend(result.records)
        unallocated[day] = result.heat_unallocated_kwh
    return all_records, unallocated


def room_records_by_id(records: Iterable[DailyRoomRecord]) -> dict[str, list[DailyRoomRecord]]:
    """Group room records by ``room_id`` (date-sorted)."""
    grouped: dict[str, list[DailyRoomRecord]] = {}
    for record in records:
        grouped.setdefault(record.room_id, []).append(record)
    for rows in grouped.values():
        rows.sort(key=lambda item: item.date)
    return grouped


def usable_room_records(records: Iterable[DailyRoomRecord]) -> list[DailyRoomRecord]:
    """Records that have heat and no room-exclusion flag."""
    return [
        record
        for record in records
        if is_room_usable(record.flags) and record.heat_room_kwh is not None
    ]
