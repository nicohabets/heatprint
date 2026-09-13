"""Effective temperature presets and TAC weighting (METHODS section 3)."""

from __future__ import annotations

import math
from datetime import date

import pytest

from heatprint_core.methods.effective_temperature import (
    preset,
    t_eff,
    tac_for_day,
    tac_series,
    weather_partial,
)
from heatprint_core.models import DailyWeather

DAY = date(2026, 1, 10)


def test_preset_table() -> None:
    none = preset("none")
    assert (none.c_lin, none.c_sqrt, none.c_sun, none.w0, none.w1) == (0, 0, 0, 1, 0)
    knmi = preset("knmi")
    assert knmi.c_lin == pytest.approx(1 / 1.5)
    assert knmi.w0 == 1 and knmi.w1 == 0
    pbl = preset("pbl")
    assert pbl.c_lin == pytest.approx(1 / 1.5) and pbl.c_sqrt == 0 and pbl.c_sun == 0
    assert (pbl.w0, pbl.w1) == (0.65, 0.35)
    pbl_sqrt = preset("pbl", pbl_wind_mode="sqrt", include_sun=True)
    assert pbl_sqrt.c_lin == 0 and pbl_sqrt.c_sqrt == pytest.approx(1 / 0.35)
    assert pbl_sqrt.c_sun == pytest.approx(1 / 480)
    house = preset("house")
    assert not house.uses_wind and (house.w0, house.w1) == (0.65, 0.35)
    with pytest.raises(ValueError):
        preset("unknown")
    with pytest.raises(ValueError):
        preset("pbl", pbl_wind_mode="cubic")


def test_knmi_effective_temperature() -> None:
    weather = DailyWeather(DAY, t_mean=5.0, wind_mean=3.0)
    assert t_eff(weather, preset("knmi")) == pytest.approx(3.0)
    assert t_eff(weather, preset("none")) == 5.0


def test_pbl_sqrt_and_sun_terms() -> None:
    weather = DailyWeather(DAY, t_mean=5.0, wind_mean=4.0, radiation=480.0)
    value = t_eff(weather, preset("pbl", pbl_wind_mode="sqrt", include_sun=True))
    assert value == pytest.approx(5.0 - math.sqrt(4.0) / 0.35 + 1.0)


def test_missing_wind_falls_back_and_is_partial() -> None:
    weather = DailyWeather(DAY, t_mean=5.0, wind_mean=None)
    assert t_eff(weather, preset("knmi")) == 5.0
    assert weather_partial(weather, preset("knmi"))
    assert not weather_partial(weather, preset("none"))
    sunny = DailyWeather(DAY, t_mean=5.0, wind_mean=2.0, radiation=None)
    assert weather_partial(sunny, preset("pbl", include_sun=True))
    assert not weather_partial(sunny, preset("pbl"))


def test_tac_weighting_with_previous_day() -> None:
    yesterday = DailyWeather(date(2026, 1, 9), t_mean=1.0, wind_mean=0.0)
    today = DailyWeather(DAY, t_mean=5.0, wind_mean=0.0)
    point = tac_for_day(today, yesterday, preset("pbl"))
    assert point.tac == pytest.approx(0.65 * 5.0 + 0.35 * 1.0)
    assert not point.partial


def test_tac_first_day_and_gap_are_partial() -> None:
    today = DailyWeather(DAY, t_mean=5.0, wind_mean=0.0)
    first = tac_for_day(today, None, preset("pbl"))
    assert first.tac == 5.0 and first.partial
    two_days_ago = DailyWeather(date(2026, 1, 8), t_mean=1.0, wind_mean=0.0)
    gap = tac_for_day(today, two_days_ago, preset("pbl"))
    assert gap.tac == 5.0 and gap.partial
    # Presets without inertia never need yesterday.
    assert not tac_for_day(today, None, preset("knmi")).partial


def test_tac_series_sorted() -> None:
    weathers = [
        DailyWeather(date(2026, 1, 11), t_mean=3.0, wind_mean=0.0),
        DailyWeather(date(2026, 1, 9), t_mean=1.0, wind_mean=0.0),
        DailyWeather(date(2026, 1, 10), t_mean=5.0, wind_mean=0.0),
    ]
    series = tac_series(weathers, preset("house"))
    assert [p.date for p in series] == [date(2026, 1, 9), date(2026, 1, 10), date(2026, 1, 11)]
    assert [p.partial for p in series] == [True, False, False]
    assert series[2].tac == pytest.approx(0.65 * 3.0 + 0.35 * 5.0)
