"""Climatology per day of year with Feb 29 folding (METHODS section 8.1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from heatprint_core.models import DailyWeather
from heatprint_core.weather.climatology import (
    build_climatology,
    climatology_value,
    leap_doy,
    remaining_season_dd,
    season_dd_clim,
)


def test_leap_doy_mapping() -> None:
    assert leap_doy(date(2025, 1, 1)) == 1
    assert leap_doy(date(2025, 2, 28)) == 59
    assert leap_doy(date(2024, 2, 29)) == 60
    assert leap_doy(date(2025, 3, 1)) == 61
    assert leap_doy(date(2024, 3, 1)) == 61
    assert leap_doy(date(2025, 12, 31)) == 366
    assert leap_doy(date(2024, 12, 31)) == 366


def _constant_weather(start: date, end: date, t_mean: float, wind: float) -> list[DailyWeather]:
    days = (end - start).days + 1
    return [DailyWeather(start + timedelta(days=i), t_mean, wind) for i in range(days)]


def test_means_per_day_of_year_and_feb29_folding() -> None:
    weathers = _constant_weather(date(2023, 1, 1), date(2023, 12, 31), 10.0, 4.0)
    weathers += _constant_weather(date(2024, 1, 1), date(2024, 12, 31), 20.0, 2.0)
    # Make Feb 29 2024 stand out to check the pooling with Feb 28 and Mar 1.
    weathers = [
        DailyWeather(w.date, 50.0, w.wind_mean) if w.date == date(2024, 2, 29) else w
        for w in weathers
    ]
    clim = build_climatology(weathers, years=5, site_id="s")
    assert len(clim.tac_by_doy) == 366 and len(clim.wind_by_doy) == 366
    # Mar 15 (well after the folded slot): mean of the two years.
    assert climatology_value(clim, "tac", date(2025, 3, 15)) == pytest.approx(15.0)
    assert climatology_value(clim, "wind", date(2025, 3, 15)) == pytest.approx(3.0)
    # Feb 29 slot pools Feb 28 (10, 20), Feb 29 (50) and Mar 1 (10, 20): mean 22.
    assert climatology_value(clim, "tac", date(2024, 2, 29)) == pytest.approx(22.0)
    assert clim.samples_by_doy[59] == 5
    assert clim.samples_by_doy[0] == 2
    assert set(clim.dd_by_doy) >= {"classic", "classic_unweighted", "knmi14", "pbl", "house"}
    # Classic degree days on Jan 15: mean of (18-10)x1.1 and 0 (20 > 18) = 4.4.
    assert climatology_value(clim, "classic", date(2026, 1, 15)) == pytest.approx(4.4)


def test_years_window_and_missing_days() -> None:
    old = _constant_weather(date(2000, 1, 1), date(2000, 12, 31), 0.0, 1.0)
    recent = _constant_weather(date(2024, 1, 1), date(2024, 6, 30), 10.0, 1.0)
    clim = build_climatology(old + recent, years=3)
    assert climatology_value(clim, "tac", date(2026, 3, 15)) == pytest.approx(10.0)
    assert climatology_value(clim, "tac", date(2026, 9, 15)) is None
    assert climatology_value(clim, "nonexistent", date(2026, 3, 15)) is None


def test_remaining_season_dd_and_house_derivation() -> None:
    weathers = _constant_weather(date(2024, 1, 1), date(2024, 12, 31), 5.0, 0.0)
    clim = build_climatology(weathers, years=2)
    # knmi14: 14 - 5 = 9 per day; 10 days remaining -> 90.
    assert remaining_season_dd(
        clim, "knmi14", date(2026, 3, 1), date(2026, 3, 10)
    ) == pytest.approx(90.0)
    assert remaining_season_dd(clim, "knmi14", date(2026, 3, 11), date(2026, 3, 10)) == 0.0
    # House: stored series uses the fallback balance temp 15.5 -> 10.5 per day.
    assert season_dd_clim(clim, "house", date(2026, 3, 1), date(2026, 3, 2)) == pytest.approx(21.0)
    # Without a stored house series the value is derived from the TAC climatology.
    clim.dd_by_doy.pop("house")
    assert season_dd_clim(
        clim, "house", date(2026, 3, 1), date(2026, 3, 2), balance_temp=15.0
    ) == pytest.approx(20.0)


def test_build_from_records_uses_stored_values() -> None:
    from heatprint_core.models import DailyRecord

    records = [
        DailyRecord(
            date(2024, 1, 1) + timedelta(days=i),
            "s",
            tac_house=2.0,
            wind_mean=3.0,
            dd={"pbl": 12.0},
        )
        for i in range(60)
    ]
    clim = build_climatology(records, years=1, site_id="s")
    assert clim.site_id == "s"
    assert climatology_value(clim, "tac", date(2026, 1, 20)) == 2.0
    assert climatology_value(clim, "pbl", date(2026, 1, 20)) == 12.0
    with pytest.raises(ValueError):
        build_climatology([], years=1)
