"""End-to-end daily pipeline on a synthetic hybrid (gas boiler + heat pump) site."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from heatprint_core.flags import Flag
from heatprint_core.models import (
    DailyWeather,
    DhwConfig,
    DhwMode,
    Generator,
    GeneratorKind,
    Period,
    Role,
    SignatureFit,
    Site,
)
from heatprint_core.pipeline import build_daily_records, estimate_baselines

START = date(2026, 1, 1)
GAS_KWH = 8.792 * 0.95


def _hybrid_site() -> Site:
    return Site(
        id="home",
        generators=[
            Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER),
            Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE),
        ],
    )


def _weather(days: int) -> dict[date, DailyWeather]:
    return {
        START + timedelta(days=i): DailyWeather(START + timedelta(days=i), 2.0 + i, 3.0, 200.0)
        for i in range(days)
    }


def test_hybrid_ten_days() -> None:
    site = _hybrid_site()
    weather = _weather(10)
    gas = {START + timedelta(days=i): (5.0 - 0.3 * i, set()) for i in range(10)}
    del gas[START + timedelta(days=5)]  # a day without gas data inside the gas range
    gas[START + timedelta(days=8)] = (2.6, {Flag.INTERPOLATED})
    hp_electric = {START + timedelta(days=i): (6.0, set()) for i in range(2, 10)}
    hp_thermal = {START + timedelta(days=i): (20.0, set()) for i in range(2, 10)}
    # The weather of day 4 is provisional and day 10 has no weather.
    weather[START + timedelta(days=3)] = DailyWeather(
        START + timedelta(days=3), 5.0, 3.0, 200.0, provisional=True
    )
    del weather[START + timedelta(days=9)]

    records = build_daily_records(
        site,
        weather,
        {"boiler": gas, "hp": hp_electric},
        thermal_by_generator={"hp": hp_thermal},
        baselines={"boiler": 0.5, "hp": None},
        prices={"boiler": 1.30, "hp": 0.25},
    )
    assert [r.date for r in records] == [START + timedelta(days=i) for i in range(10)]

    day1 = records[0]
    assert day1.heat_dhw_kwh == pytest.approx(0.5 * GAS_KWH)
    assert day1.heat_space_kwh == pytest.approx(4.5 * GAS_KWH)
    assert day1.share_heat_pump == 0.0  # heat pump not installed yet: no ENERGY_MISSING
    assert day1.gas_m3 == 5.0 and day1.electric_kwh == 0.0
    assert day1.cost_eur == pytest.approx(6.5)
    assert day1.co2_kg == pytest.approx(5.0 * 1.78)
    assert Flag.ENERGY_MISSING not in day1.flags
    assert Flag.WEATHER_PARTIAL in day1.flags  # no previous day for the TAC
    assert Flag.HOUSE_NOT_FITTED in day1.flags
    assert day1.dd["classic"] == pytest.approx(16.0 * 1.1)
    assert day1.dd["knmi14"] == pytest.approx(14.0)
    assert day1.usable

    day3 = records[2]
    gas_space = 4.4 * GAS_KWH - 0.5 * GAS_KWH
    assert day3.heat_space_kwh == pytest.approx(gas_space + 20.0)
    assert day3.share_heat_pump == pytest.approx(20.0 / (gas_space + 20.0))
    assert day3.electric_kwh == 6.0
    assert day3.heat_by_generator["hp"].cop_day == pytest.approx(20.0 / 6.0)
    assert day3.heat_by_generator["hp"].heat_dhw_kwh == 0.0
    assert Flag.HEAT_ESTIMATED not in day3.flags
    assert day3.cost_eur == pytest.approx(4.4 * 1.30 + 6.0 * 0.25)
    assert day3.co2_kg == pytest.approx(4.4 * 1.78 + 6.0 * 0.30)

    assert Flag.WEATHER_PROVISIONAL in records[3].flags
    day6 = records[5]
    assert Flag.ENERGY_MISSING in day6.flags
    assert day6.heat_space_kwh == pytest.approx(20.0)
    assert not day6.usable
    assert Flag.INTERPOLATED in records[8].flags and records[8].usable
    day10 = records[9]
    assert Flag.WEATHER_MISSING in day10.flags
    assert day10.dd == {} and day10.t_mean is None
    assert day10.heat_space_kwh > 0


def test_estimated_heat_pump_and_house_fit() -> None:
    site = _hybrid_site()
    weather = _weather(3)
    gas = {d: (3.0, set()) for d in weather}
    hp_electric = {d: (5.0, set()) for d in weather}
    fit = SignatureFit(
        site_id="home",
        period=Period(date(2025, 10, 1), date(2025, 12, 31)),
        tac_preset="house",
        balance_temp=14.0,
        intercept_a=0.0,
        slope_b=2.0,
        wind_c=None,
        ua_w_per_k=83.3,
        r2=0.9,
        rmse=1.0,
        n_days=90,
        n_heating_days=80,
        ci95_slope=(1.9, 2.1),
        ci95_balance=(13.5, 14.5),
        fitted_at=datetime(2026, 1, 1),
    )
    records = build_daily_records(
        site,
        weather,
        {"boiler": gas, "hp": hp_electric},
        baselines={"boiler": None, "hp": None},
        house_fit=fit,
        outlier_dates=[START + timedelta(days=1)],
    )
    day2 = records[1]
    assert Flag.HEAT_ESTIMATED in day2.flags
    assert Flag.HOUSE_NOT_FITTED not in day2.flags
    assert day2.heat_by_generator["hp"].heat_space_kwh == pytest.approx(5.0 * 3.5)
    assert day2.heat_by_generator["hp"].cop_day is None
    # tac_house on day 2 = 0.65 x 3 + 0.35 x 2 = 2.65 -> house dd = 14 - 2.65
    assert day2.dd["house"] == pytest.approx(14.0 - 2.65)
    assert Flag.OUTLIER in day2.flags and not day2.usable
    assert Flag.OUTLIER not in records[0].flags
    assert day2.cost_eur is None


def test_no_generator_data_is_energy_missing() -> None:
    site = _hybrid_site()
    records = build_daily_records(site, _weather(2), {})
    assert all(Flag.ENERGY_MISSING in r.flags for r in records)
    assert all(r.share_heat_pump is None for r in records)


def test_baseline_estimation_convention() -> None:
    boiler = Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER)
    heat_pump = Generator.for_kind(
        "hp", "WP", GeneratorKind.HEAT_PUMP, dhw=DhwConfig(mode=DhwMode.BASELINE)
    )
    site = Site(id="home", generators=[boiler, heat_pump])
    summer = {date(2025, 6, 1) + timedelta(days=i): (0.5, set()) for i in range(92)}
    winter = {date(2025, 12, 1) + timedelta(days=i): (4.0, set()) for i in range(31)}
    thermal = {d: (2.0, set()) for d in summer} | {d: (30.0, set()) for d in winter}
    baselines = estimate_baselines(site, {"boiler": summer | winter}, {"hp": thermal})
    assert baselines["boiler"] == pytest.approx(0.5)  # m3 per day
    assert baselines["hp"] == pytest.approx(2.0)  # kWh heat per day (thermal series)
    weather = {d: DailyWeather(d, 2.0, 3.0) for d in winter}
    records = build_daily_records(
        site, weather, {"boiler": winter}, thermal_by_generator={"hp": thermal}, baselines=baselines
    )
    # Records start at the first energy day (June); pick a winter day.
    winter_day = next(r for r in records if r.date == date(2025, 12, 6))
    hp_energy = winter_day.heat_by_generator["hp"]
    assert hp_energy.heat_dhw_kwh == pytest.approx(2.0)
    assert hp_energy.heat_space_kwh == pytest.approx(28.0)
    assert hp_energy.electric_kwh is None and hp_energy.carrier_amount is None
    summer_day = next(r for r in records if r.date == date(2025, 7, 1))
    assert summer_day.heat_by_generator["hp"].heat_space_kwh == 0.0
    assert Flag.WEATHER_MISSING in summer_day.flags


def test_start_end_window() -> None:
    site = _hybrid_site()
    weather = _weather(10)
    gas = {d: (3.0, set()) for d in weather}
    records = build_daily_records(
        site,
        weather,
        {"boiler": gas},
        start=START + timedelta(days=2),
        end=START + timedelta(days=4),
    )
    assert [r.date for r in records] == [START + timedelta(days=i) for i in (2, 3, 4)]
    # Yesterday's weather (outside the window) still feeds the TAC of the first day.
    assert Flag.WEATHER_PARTIAL not in records[0].flags
