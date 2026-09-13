"""Extra spec checks against METHODS.md added during review (sections 3, 4, 6, 8.5, 9)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pytest

from heatprint_core.analysis.forecast import forecast_season
from heatprint_core.constants import MONTH_WEIGHTS
from heatprint_core.dhw import estimate_baseline, summer_window
from heatprint_core.flags import Flag
from heatprint_core.methods.degree_days import compute_day, dd_classic
from heatprint_core.methods.pbl_params import pbl_params
from heatprint_core.models import (
    Climatology,
    DailyEnergy,
    DailyRecord,
    DailyWeather,
    DhwConfig,
    DhwMode,
    Generator,
    GeneratorKind,
    MethodConfig,
    PblParams,
    Role,
    Season,
    Site,
)
from heatprint_core.pipeline import build_daily_records
from heatprint_core.readings import readings_to_daily

# METHODS 4.3, PBL table 3.4 (practical) and 3.3 (optimal): (TST, RER, TOP) per month.
PBL_PRACTICAL_BY_MONTH = {
    **dict.fromkeys((12, 1, 2), (17.01, 1.00, 1.30)),
    **dict.fromkeys((3, 11), (15.26, 1.02, 1.30)),
    **dict.fromkeys((4, 10), (15.10, 0.79, 1.30)),
    **dict.fromkeys((5, 6, 7, 8, 9), (13.92, 0.61, 1.30)),
}
PBL_OPTIMAL_BY_MONTH = {
    **dict.fromkeys((12, 1, 2), (14.91, 1.00, 1.32)),
    **dict.fromkeys((3, 11), (15.09, 0.96, 1.32)),
    **dict.fromkeys((4, 10), (15.52, 0.82, 1.32)),
    **dict.fromkeys((5, 6, 7, 8, 9), (15.15, 0.73, 1.32)),
}
# METHODS 4.1: mindergas month weights.
MINDERGAS_WEIGHTS = {
    **dict.fromkeys((11, 12, 1, 2), 1.1),
    **dict.fromkeys((3, 10), 1.0),
    **dict.fromkeys((4, 5, 6, 7, 8, 9), 0.8),
}


@pytest.mark.parametrize("month", range(1, 13))
def test_pbl_tables_every_month(month: int) -> None:
    practical = pbl_params(month, "practical")
    assert (practical.tst, practical.rer, practical.top) == PBL_PRACTICAL_BY_MONTH[month]
    optimal = pbl_params(month, "optimal")
    assert (optimal.tst, optimal.rer, optimal.top) == PBL_OPTIMAL_BY_MONTH[month]


@pytest.mark.parametrize("month", range(1, 13))
def test_mindergas_weights_every_month(month: int) -> None:
    assert MONTH_WEIGHTS[month] == MINDERGAS_WEIGHTS[month]
    weighted, unweighted = dd_classic(8.0, month)
    assert unweighted == pytest.approx(10.0)
    assert weighted == pytest.approx(10.0 * MINDERGAS_WEIGHTS[month])


def test_compute_day_pbl_sqrt_wind_mode_with_sun_and_inertia() -> None:
    """PBL 2022 eq. 17/20: TAC = 0.65*(T-√W+Q/480) + 0.35*(T-1-√W-1+Q-1/480)."""
    yesterday = DailyWeather(date(2026, 1, 9), t_mean=2.0, wind_mean=9.0, radiation=240.0)
    today = DailyWeather(date(2026, 1, 10), t_mean=6.0, wind_mean=4.0, radiation=480.0)
    config = MethodConfig(pbl=PblParams(wind_mode="sqrt", include_sun=True))
    result = compute_day(today, yesterday, config)
    t_eff_today = 6.0 - math.sqrt(4.0) + 480.0 / 480
    t_eff_yesterday = 2.0 - math.sqrt(9.0) + 240.0 / 480
    tac = 0.65 * t_eff_today + 0.35 * t_eff_yesterday
    assert result.tac_pbl == pytest.approx(tac)
    assert result.dd["pbl"] == pytest.approx(1.00 * (17.01 - tac))
    # The KNMI and house presets ignore the PBL wind mode and the sun term.
    assert result.t_eff_knmi == pytest.approx(6.0 - 4.0 / 1.5)
    assert result.tac_house == pytest.approx(0.65 * 6.0 + 0.35 * 2.0)
    assert Flag.WEATHER_PARTIAL not in result.flags
    # Sun requested but no radiation: fall back to the temperature/wind variant, flagged.
    no_sun = DailyWeather(date(2026, 1, 10), t_mean=6.0, wind_mean=4.0, radiation=None)
    partial = compute_day(no_sun, None, config)
    assert partial.tac_pbl == pytest.approx(6.0 - math.sqrt(4.0))
    assert Flag.WEATHER_PARTIAL in partial.flags


def test_readings_across_month_boundary_with_dst_fall_back() -> None:
    """25 October 2026 (Europe/Amsterdam) has 25 hours; the month boundary follows."""
    readings = [
        (datetime(2026, 10, 24, 0, 0), 0.0),
        (datetime(2026, 10, 26, 12, 0), 61.0),  # 24 + 25 + 12 hours at 1 per hour
        (datetime(2026, 11, 2, 0, 0), 61.0 + 12.0 + 6 * 24.0),  # gap of 6.5 days
    ]
    daily = readings_to_daily(readings, "Europe/Amsterdam")
    assert daily[date(2026, 10, 24)] == (pytest.approx(24.0), set())
    assert daily[date(2026, 10, 25)] == (pytest.approx(25.0), set())
    for day in (date(2026, 10, 27), date(2026, 10, 31), date(2026, 11, 1)):
        amount, flags = daily[day]
        assert amount == pytest.approx(24.0)
        assert flags == {Flag.INTERPOLATED}
    # 26 October: 12 measured hours plus 12 interpolated hours.
    assert daily[date(2026, 10, 26)][0] == pytest.approx(24.0)
    assert daily[date(2026, 10, 26)][1] == {Flag.INTERPOLATED}
    assert date(2026, 11, 2) not in daily
    assert sorted(daily) == [date(2026, 10, 24) + timedelta(days=i) for i in range(9)]


def test_pipeline_dhw_split_with_measured_sensor() -> None:
    """METHODS 6 measured: Q_dhw from the sensor, Q_space = Q_total - Q_dhw (min 0)."""
    heat_pump = Generator.for_kind(
        "hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.BOTH, dhw=DhwConfig(mode=DhwMode.MEASURED)
    )
    site = Site(id="home", generators=[heat_pump])
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(3)]
    weather = {d: DailyWeather(d, 3.0, 2.0) for d in days}
    electric = {d: (8.0, set()) for d in days}
    thermal = {d: (28.0, set()) for d in days}
    dhw = {days[0]: (6.0, set()), days[1]: (40.0, set())}  # day 3 has no measurement
    records = build_daily_records(
        site,
        weather,
        {"hp": electric},
        thermal_by_generator={"hp": thermal},
        dhw_by_generator={"hp": dhw},
        baselines={"hp": 1.0},
    )
    day1 = records[0].heat_by_generator["hp"]
    assert (day1.heat_total_kwh, day1.heat_dhw_kwh, day1.heat_space_kwh) == (28.0, 6.0, 22.0)
    assert day1.cop_day == pytest.approx(28.0 / 8.0)
    assert Flag.HEAT_ESTIMATED not in records[0].flags
    # A measured DHW amount above the total heat leaves no space heating (never negative).
    day2 = records[1].heat_by_generator["hp"]
    assert (day2.heat_dhw_kwh, day2.heat_space_kwh) == (40.0, 0.0)
    # Without a measurement the baseline (carrier units x actual conversion) is used.
    day3 = records[2].heat_by_generator["hp"]
    assert day3.heat_dhw_kwh == pytest.approx(1.0 * 28.0 / 8.0)
    assert day3.heat_space_kwh == pytest.approx(28.0 - 3.5)
    assert Flag.DHW_BASELINE_MISSING not in records[2].flags
    assert records[0].heat_dhw_kwh == 6.0 and records[0].heat_space_kwh == 22.0

    missing = build_daily_records(
        site,
        weather,
        {"hp": electric},
        thermal_by_generator={"hp": thermal},
        dhw_by_generator={"hp": {}},
        baselines={"hp": None},
    )
    assert Flag.DHW_BASELINE_MISSING in missing[0].flags
    assert missing[0].heat_by_generator["hp"].heat_dhw_kwh == 0.0
    assert missing[0].heat_by_generator["hp"].heat_space_kwh == 28.0


def test_forecast_reports_space_and_dhw_separately() -> None:
    """METHODS 8.5: space heating and DHW are forecast and reported apart."""
    season = Season("2025/26", date(2025, 10, 1), date(2026, 3, 31))
    records = []
    for i in range(30):
        day = season.start + timedelta(days=i)
        energy = DailyEnergy(day, "boiler", 2.0, 0.0, 15.0, 5.0, 10.0)
        records.append(
            DailyRecord(
                date=day,
                site_id="s",
                dd={"classic": 5.0},
                heat_space_kwh=10.0,
                heat_dhw_kwh=5.0,
                heat_by_generator={"boiler": energy},
            )
        )
    clim = Climatology(
        site_id="s",
        years=20,
        tac_by_doy=[5.0] * 366,
        wind_by_doy=[3.0] * 366,
        dd_by_doy={"classic": [4.0] * 366},
        computed_at=date(2026, 1, 1),
    )
    forecast = forecast_season(records, season, clim, "classic", dhw_per_day=5.0)
    remaining = (season.end - records[-1].date).days
    assert forecast.k_ytd == pytest.approx(2.0)
    assert forecast.heat_space_ytd == pytest.approx(300.0)
    assert forecast.heat_space_forecast == pytest.approx(300.0 + 2.0 * 4.0 * remaining)
    assert forecast.heat_dhw_forecast == pytest.approx(150.0 + 5.0 * remaining)
    assert forecast.days_remaining == remaining
    # The single generator carries the whole forecast: year-to-date total heat plus
    # the remaining space heating and DHW.
    assert forecast.per_generator["boiler"] == pytest.approx(
        30 * 15.0 + 2.0 * 4.0 * remaining + 5.0 * remaining
    )


def test_summer_window_clamps_invalid_days_and_baseline_min_days_zero() -> None:
    """Regression: 02-29 in a common year and 06-31 must not raise; min_days=0 no ZeroDivision."""
    assert summer_window(2025, "02-29", "06-31") == (date(2025, 2, 28), date(2025, 6, 30))
    assert summer_window(2024, "02-29", "08-31") == (date(2024, 2, 29), date(2024, 8, 31))
    series = {date(2025, 12, 1) + timedelta(days=i): 2.0 for i in range(40)}
    # No summer data at all: the summer window is empty and the rolling fallback is used.
    assert estimate_baseline(series, min_days=0) == pytest.approx(2.0)
