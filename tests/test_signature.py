"""Synthetic house: signature fit and NAC saving (METHODS sections 7, 8.2 and 11)."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from heatprint_core.analysis.normalize import normalized_consumption, saving_between
from heatprint_core.analysis.signature import fit_signature, residuals_by_date
from heatprint_core.flags import Flag
from heatprint_core.models import DailyRecord, Period
from heatprint_core.weather.climatology import build_climatology, climatology_value
from tests.conftest import synthetic_records, synthetic_weather

A, B1, B2, TB, C, SIGMA = 1.0, 2.5, 2.0, 15.0, 0.5, 2.0
N_DAYS = 181  # 1 September - 28 February


@pytest.fixture(scope="module")
def synthetic_house() -> dict[str, object]:
    rng = random.Random(7)
    weather_1 = synthetic_weather(date(2024, 9, 1), N_DAYS, rng)
    weather_2 = synthetic_weather(date(2025, 9, 1), N_DAYS, rng)
    records_1 = synthetic_records(weather_1, A, B1, TB, C, SIGMA, rng)
    records_2 = synthetic_records(weather_2, A, B2, TB, C, SIGMA, rng)
    period_1 = Period(weather_1[0].date, weather_1[-1].date, "2024/25")
    period_2 = Period(weather_2[0].date, weather_2[-1].date, "2025/26")
    climatology = build_climatology(
        weather_1 + weather_2, years=5, site_id="synth", house_balance_temp=TB
    )
    return {
        "records_1": records_1,
        "records_2": records_2,
        "period_1": period_1,
        "period_2": period_2,
        "climatology": climatology,
    }


def test_fit_recovers_parameters(synthetic_house: dict[str, object]) -> None:
    fit = fit_signature(synthetic_house["records_1"], synthetic_house["period_1"])
    assert fit is not None
    assert abs(fit.slope_b - B1) / B1 < 0.05
    assert abs(fit.balance_temp - TB) < 0.5
    assert abs(fit.wind_c - C) < 0.3
    assert abs(fit.intercept_a - A) < 3.0
    assert fit.n_days == N_DAYS and fit.n_heating_days >= 15
    assert fit.r2 > 0.9
    assert 1.5 < fit.rmse < 2.6
    assert fit.ci95_slope[0] < B1 < fit.ci95_slope[1]
    assert fit.ci95_balance[0] <= TB <= fit.ci95_balance[1]
    assert fit.ua_w_per_k == pytest.approx(fit.slope_b * 1000 / 24)
    assert fit.tac_preset == "house" and fit.site_id == "synth"
    assert fit.outliers == []

    fit_2 = fit_signature(synthetic_house["records_2"], synthetic_house["period_2"])
    assert fit_2 is not None
    assert abs(fit_2.slope_b - B2) / B2 < 0.05
    assert abs(fit_2.balance_temp - TB) < 0.5


def test_fit_without_wind_term(synthetic_house: dict[str, object]) -> None:
    fit = fit_signature(synthetic_house["records_1"], synthetic_house["period_1"], fit_wind=False)
    assert fit is not None
    assert fit.wind_c is None
    assert abs(fit.slope_b - B1) / B1 < 0.06


def test_outlier_detection_and_refit(synthetic_house: dict[str, object]) -> None:
    records: list[DailyRecord] = list(synthetic_house["records_1"])
    spoiled = records[40]
    records[40] = replace(spoiled, heat_space_kwh=spoiled.heat_space_kwh + 60.0)
    fit = fit_signature(records, synthetic_house["period_1"])
    assert fit is not None
    assert fit.outliers == [spoiled.date]
    assert fit.n_days == N_DAYS - 1
    assert abs(fit.slope_b - B1) / B1 < 0.05
    residuals = residuals_by_date(fit, records)
    assert abs(residuals[spoiled.date]) > 50


def test_exclusion_flags_and_minimums(synthetic_house: dict[str, object]) -> None:
    records: list[DailyRecord] = list(synthetic_house["records_1"])
    period: Period = synthetic_house["period_1"]
    flagged = [
        replace(r, flags={Flag.ENERGY_MISSING}) if i % 2 else r for i, r in enumerate(records)
    ]
    fit = fit_signature(flagged, period)
    assert fit is not None and fit.n_days == len([r for r in flagged if not r.flags])
    assert fit_signature(records[:20], period) is None
    assert fit_signature(records, period, min_days=500) is None
    # A period with only warm days has no balance temperature with enough heating days.
    warm = [replace(r, tac_house=25.0) for r in records]
    assert fit_signature(warm, period) is None


def test_saving_between_with_bootstrap(synthetic_house: dict[str, object]) -> None:
    records_1 = synthetic_house["records_1"]
    records_2 = synthetic_house["records_2"]
    period_1: Period = synthetic_house["period_1"]
    climatology = synthetic_house["climatology"]
    fit_1 = fit_signature(records_1, period_1)
    fit_2 = fit_signature(records_2, synthetic_house["period_2"])
    assert fit_1 is not None and fit_2 is not None

    # True saving of the synthetic house on the same climatology (the slope drops 20%,
    # the intercept and wind term do not, so the NAC saving is a little below 20%).
    def true_nac(slope: float) -> float:
        total = 0.0
        day = period_1.start
        while day <= period_1.end:
            tac = climatology_value(climatology, "tac", day)
            wind = climatology_value(climatology, "wind", day)
            total += A + slope * max(0.0, TB - tac) + C * wind
            day += timedelta(days=1)
        return total

    true_saving = (true_nac(B1) - true_nac(B2)) / true_nac(B1) * 100
    assert 15.0 < true_saving < 20.0

    saving, interval = saving_between(
        fit_1, fit_2, climatology, records_1, records_2, n_boot=50, seed=42
    )
    assert interval is not None
    assert interval[0] <= true_saving <= interval[1]
    assert abs(saving - 20.0) < 5.0
    assert interval[0] < saving < interval[1]
    assert interval[1] - interval[0] < 10.0
    nac_1 = normalized_consumption(fit_1, climatology, period_1)
    assert nac_1 == pytest.approx(true_nac(B1), rel=0.05)


def test_fit_falls_back_to_no_wind_when_wind_missing(synthetic_house: dict[str, object]) -> None:
    records: list[DailyRecord] = [replace(r, wind_mean=None) for r in synthetic_house["records_1"]]
    fit = fit_signature(records, synthetic_house["period_1"], fit_wind=True)
    assert fit is not None
    assert fit.wind_c is None
    assert abs(fit.slope_b - B1) / B1 < 0.06
    # Days without wind are dropped when enough days with wind remain.
    mixed = records[:20] + list(synthetic_house["records_1"])[20:]
    fit = fit_signature(mixed, synthetic_house["period_1"], fit_wind=True)
    assert fit is not None
    assert fit.wind_c is not None and fit.n_days == N_DAYS - 20
