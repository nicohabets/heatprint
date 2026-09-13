"""Meter readings to daily consumption (METHODS section 9)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from heatprint_core.flags import Flag
from heatprint_core.readings import daily_amounts, readings_to_daily

TZ = "Europe/Amsterdam"


def test_daily_readings_at_midnight() -> None:
    readings = [(datetime(2026, 1, d, 0, 0), 100.0 + 2.5 * (d - 1)) for d in range(1, 5)]
    daily = readings_to_daily(readings, TZ)
    assert sorted(daily) == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    for amount, flags in daily.values():
        assert amount == pytest.approx(2.5)
        assert flags == set()


def test_interpolation_and_partial_days() -> None:
    readings = [
        (datetime(2026, 1, 1, 8, 0), 100.0),
        (datetime(2026, 1, 2, 8, 0), 110.0),
        (datetime(2026, 1, 3, 20, 0), 128.0),
    ]
    daily = readings_to_daily(readings, TZ)
    # Day 1 covers 08:00-24:00 at 10/day: 6.667, partial.
    assert daily[date(2026, 1, 1)][0] == pytest.approx(10 * 16 / 24)
    assert daily[date(2026, 1, 1)][1] == {Flag.PARTIAL_DAY}
    # Day 2: 8 h at 10/day + 16 h at 12/day (18 over 36 h) = 3.333 + 8 = 11.333.
    assert daily[date(2026, 1, 2)][0] == pytest.approx(10 * 8 / 24 + 12 * 16 / 24)
    assert daily[date(2026, 1, 2)][1] == set()
    # Day 3: 20 h at 12/day, partial.
    assert daily[date(2026, 1, 3)][0] == pytest.approx(12 * 20 / 24)
    assert daily[date(2026, 1, 3)][1] == {Flag.PARTIAL_DAY}


def test_gap_longer_than_three_days_is_interpolated() -> None:
    readings = [
        (datetime(2026, 1, 1, 0, 0), 0.0),
        (datetime(2026, 1, 2, 0, 0), 10.0),
        (datetime(2026, 1, 7, 0, 0), 60.0),
        (datetime(2026, 1, 8, 0, 0), 70.0),
    ]
    daily = readings_to_daily(readings, TZ)
    assert daily[date(2026, 1, 1)] == (pytest.approx(10.0), set())
    for day in (2, 3, 4, 5, 6):
        amount, flags = daily[date(2026, 1, day)]
        assert amount == pytest.approx(10.0)
        assert flags == {Flag.INTERPOLATED}
    assert daily[date(2026, 1, 7)] == (pytest.approx(10.0), set())
    # A gap of exactly three days is not flagged.
    short = [(datetime(2026, 1, 1), 0.0), (datetime(2026, 1, 4), 30.0)]
    assert all(flags == set() for _, flags in readings_to_daily(short, TZ).values())


def test_meter_reset_starts_new_series() -> None:
    readings = [
        (datetime(2026, 1, 1, 0, 0), 100.0),
        (datetime(2026, 1, 2, 0, 0), 110.0),
        (datetime(2026, 1, 2, 12, 0), 115.0),
        (datetime(2026, 1, 2, 18, 0), 2.0),  # reset
        (datetime(2026, 1, 3, 0, 0), 4.0),
        (datetime(2026, 1, 4, 0, 0), 12.0),
    ]
    daily = readings_to_daily(readings, TZ)
    assert daily[date(2026, 1, 1)] == (pytest.approx(10.0), set())
    amount, flags = daily[date(2026, 1, 2)]
    # 5 before the reset plus 2 after it; the gap in between is unknown.
    assert amount == pytest.approx(7.0)
    assert flags == {Flag.METER_RESET}
    assert daily[date(2026, 1, 3)] == (pytest.approx(8.0), set())


def test_duplicates_and_unsorted_input() -> None:
    readings = [
        (datetime(2026, 1, 3, 0, 0), 20.0),
        (datetime(2026, 1, 1, 0, 0), 0.0),
        (datetime(2026, 1, 2, 0, 0), 9.0),
        (datetime(2026, 1, 2, 0, 0), 10.0),  # duplicate timestamp: last wins
    ]
    daily = readings_to_daily(readings, TZ)
    assert daily_amounts(daily) == {
        date(2026, 1, 1): pytest.approx(10.0),
        date(2026, 1, 2): pytest.approx(10.0),
    }


def test_aware_timestamps_use_local_days() -> None:
    # 23:30 UTC on Jan 1 is 00:30 local on Jan 2 (CET).
    readings = [
        (datetime(2026, 1, 1, 23, 30, tzinfo=UTC), 0.0),
        (datetime(2026, 1, 2, 23, 30, tzinfo=UTC), 24.0),
        (datetime(2026, 1, 3, 23, 30, tzinfo=UTC), 48.0),
    ]
    daily = readings_to_daily(readings, ZoneInfo(TZ))
    assert sorted(daily) == [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)]
    assert daily[date(2026, 1, 2)][0] == pytest.approx(23.5)
    assert daily[date(2026, 1, 2)][1] == {Flag.PARTIAL_DAY}
    assert daily[date(2026, 1, 3)][0] == pytest.approx(24.0)
    assert daily[date(2026, 1, 3)][1] == set()
    assert daily[date(2026, 1, 4)][0] == pytest.approx(0.5)


def test_dst_transition_day_has_23_hours() -> None:
    # 29 March 2026: clocks go forward, the local day has 23 hours.
    readings = [
        (datetime(2026, 3, 28, 0, 0), 0.0),
        (datetime(2026, 3, 31, 0, 0), 71.0),  # 71 hours at 1/h
    ]
    daily = readings_to_daily(readings, TZ)
    assert daily[date(2026, 3, 28)][0] == pytest.approx(24.0)
    assert daily[date(2026, 3, 29)][0] == pytest.approx(23.0)
    assert daily[date(2026, 3, 30)][0] == pytest.approx(24.0)


def test_too_few_readings() -> None:
    assert readings_to_daily([], TZ) == {}
    assert readings_to_daily([(datetime(2026, 1, 1), 5.0)], TZ) == {}
