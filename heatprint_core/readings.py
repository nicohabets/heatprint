"""Cumulative meter readings to daily consumption (METHODS section 9).

Input: a series of ``(timestamp, cumulative reading)`` pairs (Home Assistant long-term
statistics ``sum``/``state`` or a CSV import). Output: consumption per local calendar
day of the site.

1. Sort, drop duplicate timestamps and detect resets (a reading lower than the previous
   one): each reset starts a new series and the days touching the reset are flagged
   ``METER_RESET``.
2. Interpolate the reading linearly at every local midnight.
3. Daily consumption = reading(d+1 00:00) - reading(d 00:00).
4. A gap of more than ``max_gap_days`` (default 3) between two readings flags every day
   whose value depends on that gap as ``INTERPOLATED``.
5. The first and last day with incomplete coverage get ``PARTIAL_DAY`` (their amount
   covers only the measured part of the day).
"""

from __future__ import annotations

import logging
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from .flags import Flag

_LOGGER = logging.getLogger(__name__)

SECONDS_PER_DAY = 86400.0


def resolve_tz(tz: str | tzinfo) -> tzinfo:
    """Return a ``tzinfo`` for a zone name or pass an existing ``tzinfo`` through."""
    if isinstance(tz, str):
        return ZoneInfo(tz)
    return tz


def local_midnight(day: date, tz: tzinfo) -> datetime:
    """Aware datetime of 00:00 local time on ``day``."""
    return datetime.combine(day, time.min, tzinfo=tz)


def _normalize(readings: Iterable[tuple[datetime, float]], tz: tzinfo) -> list[tuple[float, float]]:
    """Localize, sort and de-duplicate readings; returns ``(unix_ts, value)`` pairs."""
    by_ts: dict[float, float] = {}
    for stamp, value in readings:
        if value is None:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=tz)
        by_ts[stamp.timestamp()] = float(value)  # duplicates: last wins
    return sorted(by_ts.items())


def _split_on_resets(points: Sequence[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Split the series into monotonic segments; a decreasing value starts a new segment."""
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in points:
        if current and point[1] < current[-1][1]:
            segments.append(current)
            current = []
        current.append(point)
    if current:
        segments.append(current)
    return segments


class _Segment:
    """One monotonic series of readings with linear interpolation."""

    def __init__(self, points: Sequence[tuple[float, float]]) -> None:
        self.ts = [p[0] for p in points]
        self.values = [p[1] for p in points]

    @property
    def first(self) -> float:
        return self.ts[0]

    @property
    def last(self) -> float:
        return self.ts[-1]

    def value_at(self, t: float) -> tuple[float, float]:
        """Interpolated value at unix time ``t`` and the length (s) of the enclosing gap."""
        index = bisect_left(self.ts, t)
        if index < len(self.ts) and self.ts[index] == t:
            return self.values[index], 0.0
        left, right = index - 1, index
        if left < 0 or right >= len(self.ts):
            raise ValueError("timestamp outside segment")
        t0, t1 = self.ts[left], self.ts[right]
        v0, v1 = self.values[left], self.values[right]
        fraction = (t - t0) / (t1 - t0)
        return v0 + fraction * (v1 - v0), t1 - t0


def readings_to_daily(
    readings: Iterable[tuple[datetime, float]],
    tz: str | tzinfo,
    max_gap_days: float = 3.0,
) -> dict[date, tuple[float, set[Flag]]]:
    """Convert cumulative readings to ``{day: (consumption, flags)}`` (METHODS section 9).

    Naive timestamps are interpreted in ``tz``; aware timestamps are converted to it.
    Days without any coverage are absent from the result. Days touching a meter reset
    contain the measured part of the consumption and carry ``METER_RESET``.
    """
    zone = resolve_tz(tz)
    points = _normalize(readings, zone)
    result: dict[date, tuple[float, set[Flag]]] = {}
    if len(points) < 2:
        return result

    segments = _split_on_resets(points)
    if len(segments) > 1:
        _LOGGER.debug("detected %d meter reset(s)", len(segments) - 1)

    max_gap_seconds = max_gap_days * SECONDS_PER_DAY
    series_first = points[0][0]
    series_last = points[-1][0]

    for segment_points in segments:
        if len(segment_points) < 2:
            continue
        segment = _Segment(segment_points)
        day = datetime.fromtimestamp(segment.first, zone).date()
        last_day = datetime.fromtimestamp(segment.last, zone).date()
        while day <= last_day:
            m0 = local_midnight(day, zone).timestamp()
            m1 = local_midnight(day + timedelta(days=1), zone).timestamp()
            t0, t1 = max(m0, segment.first), min(m1, segment.last)
            if t1 > t0:
                v0, gap0 = segment.value_at(t0)
                v1, gap1 = segment.value_at(t1)
                amount = max(0.0, v1 - v0)
                flags: set[Flag] = set()
                if t0 > m0 or t1 < m1:
                    flags.add(Flag.PARTIAL_DAY)
                if max(gap0, gap1) > max_gap_seconds:
                    flags.add(Flag.INTERPOLATED)
                previous = result.get(day)
                if previous is not None:
                    amount += previous[0]
                    flags |= previous[1]
                result[day] = (amount, flags)
            day += timedelta(days=1)

    # Flag the days that touch a reset; they are neither the true first nor last day.
    for before, after in zip(segments, segments[1:], strict=False):
        reset_start = datetime.fromtimestamp(before[-1][0], zone).date()
        reset_end = datetime.fromtimestamp(after[0][0], zone).date()
        day = reset_start
        while day <= reset_end:
            amount, flags = result.get(day, (0.0, set()))
            flags = set(flags) | {Flag.METER_RESET}
            keep_partial = day in (
                datetime.fromtimestamp(series_first, zone).date(),
                datetime.fromtimestamp(series_last, zone).date(),
            )
            if not keep_partial:
                flags.discard(Flag.PARTIAL_DAY)
            if day in result:
                result[day] = (amount, flags)
            day += timedelta(days=1)

    return dict(sorted(result.items()))


def daily_amounts(daily: dict[date, tuple[float, set[Flag]]]) -> dict[date, float]:
    """Strip the flags from the output of :func:`readings_to_daily`."""
    return {day: amount for day, (amount, _flags) in daily.items()}
