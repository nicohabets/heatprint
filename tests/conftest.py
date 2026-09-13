"""Shared fixtures and synthetic-data helpers for the heatprint_core tests."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pytest

from heatprint_core.methods.degree_days import compute_day
from heatprint_core.models import DailyRecord, DailyWeather, MethodConfig


def synthetic_weather(start: date, n_days: int, rng: random.Random) -> list[DailyWeather]:
    """Seasonal temperature curve (Jan about 2.5, Jul about 19.5 degrees C) with AR(1)
    noise and random wind, no radiation."""
    weathers: list[DailyWeather] = []
    noise = 0.0
    for i in range(n_days):
        day = start + timedelta(days=i)
        doy = day.timetuple().tm_yday
        base = 11.0 - 8.5 * math.cos(2 * math.pi * (doy - 15) / 365.0)
        noise = 0.6 * noise + rng.gauss(0, 2.5)
        wind = max(0.5, rng.gauss(4.5, 1.5))
        weathers.append(DailyWeather(day, round(base + noise, 2), round(wind, 2), None))
    return weathers


def synthetic_records(
    weathers: list[DailyWeather],
    a: float,
    b: float,
    balance_temp: float,
    c: float,
    sigma: float,
    rng: random.Random,
    site_id: str = "synth",
    method_config: MethodConfig | None = None,
) -> list[DailyRecord]:
    """Daily records of a house ``Q = a + b * max(0, T_b - TAC_house) + c * wind + noise``."""
    by_date = {w.date: w for w in weathers}
    records: list[DailyRecord] = []
    for weather in weathers:
        yesterday = by_date.get(weather.date - timedelta(days=1))
        methods = compute_day(weather, yesterday, method_config, balance_temp)
        heating = max(0.0, balance_temp - methods.tac_house)
        heat = a + b * heating + c * weather.wind_mean + rng.gauss(0, sigma)
        records.append(
            DailyRecord(
                date=weather.date,
                site_id=site_id,
                t_mean=weather.t_mean,
                wind_mean=weather.wind_mean,
                radiation=weather.radiation,
                t_eff_knmi=methods.t_eff_knmi,
                tac_pbl=methods.tac_pbl,
                tac_house=methods.tac_house,
                dd=methods.dd,
                heat_space_kwh=max(0.0, heat),
                heat_dhw_kwh=3.0,
                flags=set(),
            )
        )
    return records


@pytest.fixture
def rng() -> random.Random:
    return random.Random(7)
