"""DHW baseline and split (METHODS section 6)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from heatprint_core.dhw import estimate_baseline, lowest_rolling_mean, split_dhw, summer_window
from heatprint_core.models import (
    Conversion,
    DhwConfig,
    DhwMode,
    Generator,
    GeneratorKind,
    Role,
)


def _series(start: date, values: list[float]) -> dict[date, float]:
    return {start + timedelta(days=i): v for i, v in enumerate(values)}


def test_summer_window() -> None:
    assert summer_window(2025, "06-01", "08-31") == (date(2025, 6, 1), date(2025, 8, 31))
    assert summer_window(2025, "12-01", "02-28") == (date(2025, 12, 1), date(2026, 2, 28))
    assert summer_window(2025, (6, 1), (8, 31)) == (date(2025, 6, 1), date(2025, 8, 31))


def test_baseline_from_last_complete_summer() -> None:
    # Winter 2024/25 high, summer 2025 low, autumn 2025 rising again.
    series = _series(date(2025, 1, 1), [5.0] * 151)  # Jan 1 - May 31
    series.update(_series(date(2025, 6, 1), [0.4, 0.6] * 46))  # Jun 1 - Aug 31: mean 0.5
    series.update(_series(date(2025, 9, 1), [3.0] * 60))
    assert estimate_baseline(series) == pytest.approx(0.5)
    # An incomplete current summer is ignored in favour of the previous one.
    series.update(_series(date(2026, 6, 1), [0.1] * 20))
    assert estimate_baseline(series) == pytest.approx(0.5)


def test_baseline_fallback_rolling_mean() -> None:
    # No summer: 60 days winter data with a low stretch of 30 days at 1.0.
    series = _series(date(2025, 1, 1), [4.0] * 15 + [1.0] * 30 + [4.0] * 15)
    assert estimate_baseline(series) == pytest.approx(1.0)
    assert lowest_rolling_mean(series) == pytest.approx(1.0)
    # Shorter than 30 days: no baseline.
    assert estimate_baseline(_series(date(2025, 1, 1), [1.0] * 20)) is None
    assert estimate_baseline({}) is None


def test_baseline_needs_min_days_in_summer() -> None:
    series = _series(date(2025, 6, 1), [0.5] * 20)  # only 20 summer days
    series.update(_series(date(2025, 10, 1), [2.0] * 40))
    # Summer has too few days -> rolling fallback (lowest 30-day mean is autumn 2.0).
    assert estimate_baseline(series) == pytest.approx(2.0)
    assert estimate_baseline(series, min_days=15) == pytest.approx(0.5)


def test_split_by_role() -> None:
    dhw_only = Generator.for_kind("b", "Boiler", GeneratorKind.ELECTRIC_HEATER, role=Role.DHW)
    assert split_dhw(dhw_only, 5.0, 5.0, None) == (5.0, 0.0)
    space_only = Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE)
    assert split_dhw(space_only, 30.0, 10.0, 1.0) == (0.0, 30.0)


def test_split_baseline_uses_actual_conversion() -> None:
    boiler = Generator.for_kind("b", "CV", GeneratorKind.GAS_BOILER)
    heat_total = 10.0 * 8.792 * 0.95
    dhw, space = split_dhw(boiler, heat_total, 10.0, 0.45)
    assert dhw == pytest.approx(0.45 * 8.792 * 0.95)
    assert space == pytest.approx(heat_total - dhw)
    # Baseline larger than the day's use: everything is DHW.
    small = 0.2 * 8.792 * 0.95
    assert split_dhw(boiler, small, 0.2, 0.45) == (pytest.approx(small), 0.0)
    # No carrier amount: static conversion.
    assert split_dhw(boiler, 50.0, None, 1.0)[0] == pytest.approx(8.792 * 0.95)
    # Baseline already in kWh.
    assert split_dhw(boiler, 50.0, 10.0, 4.0, baseline_in_kwh=True) == (4.0, 46.0)
    # No baseline: everything is space heating.
    assert split_dhw(boiler, 50.0, 10.0, None) == (0.0, 50.0)


def test_split_measured_fixed_and_none() -> None:
    measured = Generator.for_kind(
        "hp", "WP", GeneratorKind.HEAT_PUMP, dhw=DhwConfig(mode=DhwMode.MEASURED)
    )
    assert split_dhw(measured, 30.0, 10.0, None, measured_dhw_kwh=8.0) == (8.0, 22.0)
    assert split_dhw(measured, 5.0, 10.0, None, measured_dhw_kwh=8.0) == (8.0, 0.0)
    # Measured mode without a measurement falls back to the baseline.
    assert split_dhw(measured, 30.0, 10.0, 1.0)[0] == pytest.approx(3.0)

    fixed = Generator.for_kind(
        "b",
        "CV",
        GeneratorKind.GAS_BOILER,
        dhw=DhwConfig(mode=DhwMode.FIXED, fixed_per_day=0.5),
        conversion=Conversion(efficiency=1.0),
    )
    heat_total = 4.0 * 8.792
    dhw, space = split_dhw(fixed, heat_total, 4.0, None)
    assert dhw == pytest.approx(0.5 * 8.792)
    assert space == pytest.approx(heat_total - dhw)
    # Without a carrier amount the static conversion is used.
    assert split_dhw(fixed, 40.0, None, None)[0] == pytest.approx(0.5 * 8.792)

    none = Generator.for_kind("b", "CV", GeneratorKind.GAS_BOILER, dhw=DhwConfig(mode=DhwMode.NONE))
    assert split_dhw(none, 40.0, 4.0, 0.5) == (0.0, 40.0)
