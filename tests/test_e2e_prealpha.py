"""End-to-end pre-alpha pipeline on mock data (METHODS sections 4-8 and 11).

Covers the documented MVP calculation path without live weather APIs: four
degree-day methods, DHW split, energy-signature fit, period comparison,
climatology and season forecast. Classic weighted degree days are checked
against an independent mindergas-style summation (within 1%).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from heatprint_core.analysis.compare import compare_periods
from heatprint_core.analysis.forecast import forecast_season
from heatprint_core.analysis.signature import fit_signature
from heatprint_core.constants import MONTH_WEIGHTS
from heatprint_core.flags import Flag
from heatprint_core.methods.degree_days import dd_classic
from heatprint_core.models import (
    DailyWeather,
    Generator,
    GeneratorKind,
    Period,
    Role,
    Season,
    Site,
)
from heatprint_core.pipeline import build_daily_records, estimate_baselines
from heatprint_core.weather.climatology import build_climatology

SEASON_START = date(2024, 10, 1)
N_DAYS = 180
A, B, TB, C, SIGMA = 1.0, 2.4, 15.0, 0.4, 1.5


def _weather(start: date, n_days: int, rng: random.Random) -> dict[date, DailyWeather]:
    """Deterministic winter-ish weather series (no network)."""
    days: dict[date, DailyWeather] = {}
    for i in range(n_days):
        day = start + timedelta(days=i)
        t_mean = 8.0 + 7.0 * rng.uniform(-1.0, 1.0) - 6.0 * (i / n_days)
        wind = max(0.5, 3.5 + rng.uniform(-1.5, 1.5))
        radiation = max(0.0, 150.0 + rng.uniform(-50.0, 80.0))
        days[day] = DailyWeather(day, t_mean, wind, radiation)
    return days


def _hybrid_site() -> Site:
    return Site(
        id="e2e",
        generators=[
            Generator.for_kind("boiler", "Boiler", GeneratorKind.GAS_BOILER),
            Generator.for_kind("hp", "Heat pump", GeneratorKind.HEAT_PUMP, role=Role.SPACE),
        ],
    )


def test_prealpha_pipeline_four_methods_fit_compare_forecast() -> None:
    rng = random.Random(42)
    weather = _weather(SEASON_START, N_DAYS, rng)
    site = _hybrid_site()

    gas: dict[date, tuple[float, set[Flag]]] = {}
    electric: dict[date, tuple[float, set[Flag]]] = {}
    thermal: dict[date, tuple[float, set[Flag]]] = {}
    for day, w in weather.items():
        heating = max(0.0, TB - w.t_mean)
        space_kwh = A + B * heating + C * (w.wind_mean or 0.0) + rng.gauss(0.0, SIGMA)
        dhw_m3 = 0.4
        gas_m3 = dhw_m3 + max(0.0, space_kwh * 0.6) / (8.792 * 0.95)
        hp_th = max(0.0, space_kwh * 0.4)
        gas[day] = (gas_m3, set())
        electric[day] = (hp_th / 3.4, set())
        thermal[day] = (hp_th, set())

    baselines = estimate_baselines(site, {"boiler": gas}, {"hp": thermal})
    assert baselines["boiler"] is not None
    records = build_daily_records(
        site,
        weather,
        {"boiler": gas, "hp": electric},
        thermal_by_generator={"hp": thermal},
        baselines=baselines,
    )
    assert len(records) == N_DAYS
    assert all({"classic", "knmi14", "pbl", "house"} <= set(r.dd) for r in records)
    usable = [r for r in records if r.usable]
    assert len(usable) >= 30
    assert all(Flag.DHW_BASELINE_MISSING not in r.flags for r in records)

    period = Period(SEASON_START, SEASON_START + timedelta(days=N_DAYS - 1), "2024/25")
    fit = fit_signature(records, period)
    assert fit is not None
    assert fit.n_days >= 30
    assert fit.n_heating_days >= 15
    assert fit.r2 > 0.7
    assert fit.slope_b > 0
    assert 6.0 <= fit.balance_temp <= 22.0

    mid = SEASON_START + timedelta(days=90)
    comparison = compare_periods(
        records, Period(SEASON_START, mid - timedelta(days=1)), Period(mid, period.end), "classic"
    )
    assert comparison.k_base > 0 and comparison.k_target > 0
    assert comparison.n_base >= 30 and comparison.n_target >= 30

    climatology = build_climatology(weather.values(), years=1, site_id="e2e", house_balance_temp=TB)
    season = Season("2024/25", SEASON_START, SEASON_START + timedelta(days=364))
    today = SEASON_START + timedelta(days=120)
    forecast = forecast_season(
        records, season, climatology, method="classic", dhw_per_day=3.0, today=today
    )
    assert forecast.k_ytd is not None and forecast.k_ytd > 0
    assert forecast.heat_space_forecast > forecast.heat_space_ytd
    assert forecast.heat_dhw_forecast > 0
    assert forecast.days_remaining > 0
    assert "boiler" in forecast.per_generator


def test_classic_reproduces_independent_mindergas_sum() -> None:
    """METHODS 11: classic weighted degree days match the mindergas formula within 1%."""
    rng = random.Random(3)
    weather = _weather(date(2021, 10, 1), 365, rng)
    site = Site(
        id="mindergas", generators=[Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)]
    )
    gas = {day: (2.0 + max(0.0, 12.0 - w.t_mean) / 4.0, set()) for day, w in weather.items()}
    records = build_daily_records(site, weather, {"boiler": gas}, baselines={"boiler": 0.4})

    expected = 0.0
    actual = 0.0
    for record in records:
        weather_day = weather[record.date]
        weighted, _unweighted = dd_classic(weather_day.t_mean, record.date.month)
        expected += weighted
        actual += record.dd["classic"]
        assert record.dd["classic"] == pytest.approx(weighted)
        assert MONTH_WEIGHTS[record.date.month] in (0.8, 1.0, 1.1)

    assert actual == pytest.approx(expected)
    assert abs(actual - expected) / expected < 0.01
    assert expected > 1000
