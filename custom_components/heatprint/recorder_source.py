"""Read long-term statistics from the recorder as per-local-day values.

Energy entities are cumulative meters (state_class total / total_increasing);
their long-term statistics carry a running ``sum`` and the recorder can return
the ``change`` per period. Weather entities (state_class measurement) provide a
``mean`` per period. All queries run in the recorder's executor via
``get_instance(hass).async_add_executor_job``.

Note: the recorder buckets a "day" period in the Home Assistant time zone. When
a site uses a different time zone the day boundaries differ by the offset
between both zones; this is documented as a known limitation.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Literal

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from heatprint_core.cost import group_hourly_by_local_day

from .history_values import value_from_sample

# Request canonical units so the core always receives m3 for gas/volume and kWh for
# every energy carrier (Wh, MWh, GJ and MJ sensors are converted by the recorder).
CANONICAL_UNITS: dict[str, str] = {"energy": "kWh", "volume": "m³"}

StatType = Literal["change", "last_reset", "max", "mean", "min", "state", "sum"]


def _day_start(day: date, tz: tzinfo) -> datetime:
    """Return the UTC datetime of local midnight at the start of ``day``."""
    return dt_util.as_utc(datetime.combine(day, datetime.min.time(), tzinfo=tz))


def _row_day(row: dict[str, Any], tz: tzinfo) -> date:
    """Return the local date of a statistics row (``start`` is a float timestamp)."""
    return datetime.fromtimestamp(float(row["start"]), tz=tz).date()


async def _async_statistics(
    hass: HomeAssistant,
    statistic_ids: set[str],
    start: date,
    end: date,
    tz: tzinfo,
    period: Literal["5minute", "day", "hour", "week", "month"],
    types: set[StatType],
    units: dict[str, str] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Run statistics_during_period in the recorder executor."""
    if not statistic_ids:
        return {}
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        _day_start(start, tz),
        _day_start(end + timedelta(days=1), tz),
        statistic_ids,
        period,
        units,
        types,
    )


async def async_daily_sums(
    hass: HomeAssistant, entity_ids: Iterable[str], start: date, end: date, tz: tzinfo
) -> dict[str, dict[date, float]]:
    """Return the consumption per local day (``change``) of cumulative entities."""
    ids = {entity_id for entity_id in entity_ids if entity_id}
    rows = await _async_statistics(hass, ids, start, end, tz, "day", {"change"}, CANONICAL_UNITS)
    result: dict[str, dict[date, float]] = {entity_id: {} for entity_id in ids}
    for statistic_id, items in rows.items():
        for row in items:
            change = row.get("change")
            if change is None:
                continue
            result.setdefault(statistic_id, {})[_row_day(row, tz)] = float(change)
    return result


def hourly_rows_by_day(
    rows: Iterable[dict[str, Any]], tz: tzinfo, value_key: str
) -> dict[date, dict[int, float]]:
    """Group hourly statistic rows by local date, keyed by the hour-start timestamp.

    The integer key is the POSIX start of the hour so electric and price series
    can be aligned without depending on clock-hour labels (DST-safe).
    """
    samples: list[tuple[float, float]] = []
    for row in rows:
        value = row.get(value_key)
        if value is None:
            continue
        samples.append((float(row["start"]), float(value)))
    return group_hourly_by_local_day(samples, tz)


async def async_hourly_changes(
    hass: HomeAssistant, entity_ids: Iterable[str], start: date, end: date, tz: tzinfo
) -> dict[str, dict[date, dict[int, float]]]:
    """Return hourly ``change`` of cumulative entities, grouped by local day."""
    ids = {entity_id for entity_id in entity_ids if entity_id}
    rows = await _async_statistics(hass, ids, start, end, tz, "hour", {"change"}, CANONICAL_UNITS)
    return {
        statistic_id: hourly_rows_by_day(items, tz, "change") for statistic_id, items in rows.items()
    }


async def async_hourly_means(
    hass: HomeAssistant, entity_ids: Iterable[str], start: date, end: date, tz: tzinfo
) -> dict[str, dict[date, dict[int, float]]]:
    """Return hourly ``mean`` of measurement entities, grouped by local day."""
    ids = {entity_id for entity_id in entity_ids if entity_id}
    rows = await _async_statistics(hass, ids, start, end, tz, "hour", {"mean"}, None)
    return {
        statistic_id: hourly_rows_by_day(items, tz, "mean") for statistic_id, items in rows.items()
    }


async def async_daily_means(
    hass: HomeAssistant, entity_ids: Iterable[str], start: date, end: date, tz: tzinfo
) -> dict[str, dict[date, float]]:
    """Return the mean per local day of measurement entities (weather sensors)."""
    ids = {entity_id for entity_id in entity_ids if entity_id}
    rows = await _async_statistics(hass, ids, start, end, tz, "day", {"mean"}, None)
    result: dict[str, dict[date, float]] = {entity_id: {} for entity_id in ids}
    for statistic_id, items in rows.items():
        for row in items:
            mean = row.get("mean")
            if mean is None:
                continue
            result.setdefault(statistic_id, {})[_row_day(row, tz)] = float(mean)
    return result


async def async_daily_metrics(
    hass: HomeAssistant,
    sum_ids: Iterable[str],
    mean_ids: Iterable[str],
    start: date,
    end: date,
    tz: tzinfo,
) -> dict[str, dict[date, float]]:
    """Read Heatprint's own external statistics back as per-day values.

    Sum metrics are returned as the ``change`` per day, mean metrics as ``mean``.
    """
    result: dict[str, dict[date, float]] = {}
    sums = {statistic_id for statistic_id in sum_ids if statistic_id}
    means = {statistic_id for statistic_id in mean_ids if statistic_id}
    if sums:
        rows = await _async_statistics(hass, sums, start, end, tz, "day", {"change"}, None)
        for statistic_id, items in rows.items():
            days = result.setdefault(statistic_id, {})
            for row in items:
                if (change := row.get("change")) is not None:
                    days[_row_day(row, tz)] = float(change)
    if means:
        rows = await _async_statistics(hass, means, start, end, tz, "day", {"mean"}, None)
        for statistic_id, items in rows.items():
            days = result.setdefault(statistic_id, {})
            for row in items:
                if (mean := row.get("mean")) is not None:
                    days[_row_day(row, tz)] = float(mean)
    for statistic_id in sums | means:
        result.setdefault(statistic_id, {})
    return result


async def async_last_sum_before(
    hass: HomeAssistant, statistic_id: str, day: date, tz: tzinfo
) -> float | None:
    """Return the running ``sum`` of an external statistic just before local midnight of ``day``.

    Used to continue the running total of sum metrics when a window is (re)written.
    """
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        _day_start(day - timedelta(days=400), tz),
        _day_start(day, tz),
        {statistic_id},
        "day",
        None,
        {"sum"},
    )
    items = rows.get(statistic_id) or []
    for row in reversed(items):
        if (value := row.get("sum")) is not None:
            return float(value)
    return None


async def async_meter_reading_at(
    hass: HomeAssistant, entity_id: str, day: date, tz: tzinfo
) -> float | None:
    """Return the meter reading (``state``) of a cumulative entity at the end of ``day - 1``.

    This equals the reading at local midnight at the start of ``day``, which is
    what mindergas.nl expects for a reading dated ``day``.
    """
    previous = day - timedelta(days=1)
    rows = await _async_statistics(
        hass, {entity_id}, previous, previous, tz, "day", {"state"}, CANONICAL_UNITS
    )
    for row in reversed(rows.get(entity_id) or []):
        if (value := row.get("state")) is not None:
            return float(value)
    return None


def _state_numeric(state: Any, *, mode: str = "auto") -> float | None:
    """Parse a recorder state into a float (heating, temperature or auto)."""
    if state is None:
        return None
    attrs = getattr(state, "attributes", None) or {}
    raw = getattr(state, "state", state)
    return value_from_sample(raw, attrs, mode=mode)


async def async_daily_from_history(
    hass: HomeAssistant,
    entity_ids: Iterable[str],
    start: date,
    end: date,
    tz: tzinfo,
    *,
    mode: str = "auto",
) -> dict[str, dict[date, float]]:
    """Time-weighted daily mean from raw recorder history (~10 days typically).

    Used when a demand entity has no long-term statistics yet (METHODS 12.1).
    ``mode`` is ``auto`` (numbers / heating states), ``heating`` (prefer
    ``hvac_action``) or ``temperature`` (climate ``current_temperature``).
    """
    ids = [entity_id for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    try:
        from homeassistant.components.recorder import history
    except ImportError:
        return {entity_id: {} for entity_id in ids}

    start_dt = _day_start(start, tz)
    end_dt = _day_start(end + timedelta(days=1), tz)

    def _load() -> dict[str, list[Any]]:
        return history.get_significant_states(
            hass, start_dt, end_dt, ids, None, True, False, False, True
        )

    try:
        states = await get_instance(hass).async_add_executor_job(_load)
    except Exception:  # noqa: BLE001 - history is a fallback
        return {entity_id: {} for entity_id in ids}

    result: dict[str, dict[date, float]] = {entity_id: {} for entity_id in ids}
    for entity_id in ids:
        samples = list(states.get(entity_id) or [])
        if not samples:
            continue
        weighted: dict[date, list[tuple[float, float]]] = {}
        for index, item in enumerate(samples):
            value = _state_numeric(item, mode=mode)
            if value is None:
                continue
            last_changed = getattr(item, "last_changed", None) or getattr(
                item, "last_updated", None
            )
            if last_changed is None:
                continue
            begin = last_changed if last_changed.tzinfo else last_changed.replace(tzinfo=tz)
            if index + 1 < len(samples):
                nxt = getattr(samples[index + 1], "last_changed", None) or getattr(
                    samples[index + 1], "last_updated", None
                )
                finish = (
                    nxt
                    if nxt is not None and nxt.tzinfo
                    else (nxt.replace(tzinfo=tz) if nxt else end_dt)
                )
            else:
                finish = end_dt
            begin = max(begin, start_dt)
            finish = min(finish, end_dt)
            if finish <= begin:
                continue
            cursor = begin
            while cursor < finish:
                day = cursor.astimezone(tz).date()
                day_end = min(finish, _day_start(day + timedelta(days=1), tz))
                seconds = (day_end - cursor).total_seconds()
                if seconds > 0:
                    weighted.setdefault(day, []).append((value, seconds))
                cursor = day_end
        for day, parts in weighted.items():
            total = sum(seconds for _value, seconds in parts)
            if total <= 0:
                continue
            result[entity_id][day] = sum(value * seconds for value, seconds in parts) / total
    return result


async def async_first_day_with_data(
    hass: HomeAssistant, entity_id: str, tz: tzinfo, max_years: int = 10
) -> date | None:
    """Return the first local day for which the entity has long-term statistics."""
    today = dt_util.now(tz).date()
    start = today - timedelta(days=365 * max_years)
    rows = await _async_statistics(
        hass, {entity_id}, start, today, tz, "month", {"change"}, CANONICAL_UNITS
    )
    months = [row for row in rows.get(entity_id) or [] if row.get("change") is not None]
    if not months:
        return None
    first_month = _row_day(months[0], tz)
    month_end = (first_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    days = await _async_statistics(
        hass, {entity_id}, first_month, month_end, tz, "day", {"change"}, CANONICAL_UNITS
    )
    for row in days.get(entity_id) or []:
        if row.get("change") is not None:
            return _row_day(row, tz)
    return first_month
