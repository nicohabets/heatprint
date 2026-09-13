"""Period comparison and measure effect (METHODS sections 8.3-8.4)."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from heatprint_core.analysis.compare import (
    InsufficientDataError,
    compare_periods,
    measure_effect,
    measure_periods,
    period_stats,
)
from heatprint_core.flags import Flag
from heatprint_core.models import DailyRecord, Period, SeasonConfig
from heatprint_core.weather.climatology import build_climatology
from tests.conftest import synthetic_records, synthetic_weather


def _records(
    start: date, days: int, heat_per_dd: float, dd: float, site: str = "s"
) -> list[DailyRecord]:
    return [
        DailyRecord(
            date=start + timedelta(days=i),
            site_id=site,
            dd={"classic": dd, "pbl": dd * 0.9},
            heat_space_kwh=heat_per_dd * dd,
        )
        for i in range(days)
    ]


def test_compare_periods_hand_checked() -> None:
    base = Period(date(2025, 1, 1), date(2025, 2, 9))  # 40 days
    target = Period(date(2026, 1, 1), date(2026, 2, 9))
    records = _records(base.start, 40, 2.0, 10.0) + _records(target.start, 40, 1.6, 12.0)
    comparison = compare_periods(records, base, target, "classic")
    assert comparison.k_base == pytest.approx(2.0)
    assert comparison.k_target == pytest.approx(1.6)
    assert comparison.delta_pct == pytest.approx(-20.0)
    assert comparison.dd_base == pytest.approx(400.0) and comparison.dd_target == pytest.approx(
        480.0
    )
    assert comparison.heat_base == pytest.approx(800.0)
    assert comparison.n_base == 40 and comparison.n_target == 40
    assert comparison.method == "classic"
    assert comparison.saving_pct is None
    pbl = compare_periods(records, base, target, "pbl")
    assert pbl.delta_pct == pytest.approx(-20.0)


def test_compare_periods_excludes_flagged_days_and_checks_minimums() -> None:
    base = Period(date(2025, 1, 1), date(2025, 2, 9))
    target = Period(date(2026, 1, 1), date(2026, 2, 9))
    records = _records(base.start, 40, 2.0, 10.0) + _records(target.start, 40, 1.6, 12.0)
    records[0] = replace(records[0], flags={Flag.WEATHER_MISSING}, heat_space_kwh=999.0)
    stats = period_stats(records, base, "classic")
    assert stats.n_days == 39 and stats.k == pytest.approx(2.0)

    with pytest.raises(InsufficientDataError, match="usable days"):
        compare_periods(records, Period(date(2025, 1, 1), date(2025, 1, 20)), target)
    warm = _records(date(2024, 1, 1), 40, 2.0, 1.0)  # 40 degree days in total
    with pytest.raises(InsufficientDataError, match="degree days"):
        compare_periods(records + warm, Period(date(2024, 1, 1), date(2024, 2, 9)), target)
    # Other methods have a lower threshold (50).
    assert (
        compare_periods(
            records + warm, Period(date(2024, 1, 1), date(2024, 2, 9)), target, "classic", min_dd=30
        ).k_base
        == 2.0
    )


def test_compare_periods_rejects_zero_degree_days() -> None:
    """min_dd=0 must not return NaN; k is undefined when Σ dd is 0."""
    period = Period(date(2025, 6, 1), date(2025, 7, 10))
    records = _records(period.start, 40, 2.0, 0.0)
    with pytest.raises(InsufficientDataError, match="no degree days"):
        compare_periods(records, period, period, "pbl", min_dd=0)


def test_measure_periods() -> None:
    before, after = measure_periods(date(2025, 6, 15), date(2026, 3, 1), SeasonConfig(10, 1))
    assert before.start == date(2023, 10, 1) and before.end == date(2025, 6, 14)
    assert after.start == date(2025, 6, 15) and after.end == date(2026, 9, 30)


def test_measure_effect_on_synthetic_house() -> None:
    rng = random.Random(11)
    weather_1 = synthetic_weather(date(2024, 9, 1), 181, rng)
    weather_2 = synthetic_weather(date(2025, 9, 1), 181, rng)
    records = synthetic_records(weather_1, 1.0, 2.5, 15.0, 0.5, 2.0, rng)
    records += synthetic_records(weather_2, 1.0, 2.0, 15.0, 0.5, 2.0, rng)
    climatology = build_climatology(weather_1 + weather_2, years=5, house_balance_temp=15.0)
    comparison, fit_before, fit_after = measure_effect(
        records, date(2025, 8, 1), SeasonConfig(10, 1), climatology, method="pbl", n_boot=10
    )
    assert fit_before is not None and fit_after is not None
    assert fit_after.slope_b < fit_before.slope_b
    assert comparison.delta_pct < 0
    assert comparison.saving_pct is not None and 10 < comparison.saving_pct < 25
    assert comparison.ci95_saving is not None
    assert comparison.nac_base is not None and comparison.nac_target is not None
    assert comparison.nac_base > comparison.nac_target
    with pytest.raises(InsufficientDataError):
        measure_effect([], date(2025, 8, 1))
