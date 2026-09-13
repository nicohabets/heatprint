"""Season forecast (METHODS section 8.5)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from heatprint_core.analysis.forecast import (
    forecast_carrier_amounts,
    forecast_season,
    generator_shares_last_days,
)
from heatprint_core.flags import Flag
from heatprint_core.models import (
    Climatology,
    DailyEnergy,
    DailyRecord,
    Generator,
    GeneratorKind,
    Period,
    Role,
    Season,
    SignatureFit,
    Site,
)

SEASON = Season("2025/26", date(2025, 10, 1), date(2026, 4, 30))


def _climatology(dd_per_day: float, tac: float = 5.0, wind: float = 4.0) -> Climatology:
    return Climatology(
        site_id="s",
        years=20,
        tac_by_doy=[tac] * 366,
        wind_by_doy=[wind] * 366,
        dd_by_doy={"pbl": [dd_per_day] * 366, "classic": [dd_per_day * 1.2] * 366},
        computed_at=date(2026, 1, 1),
    )


def _record(
    day: date, heat: float, dd: float, boiler: float, hp: float, flags: set[Flag] | None = None
) -> DailyRecord:
    energies = {
        "boiler": DailyEnergy(day, "boiler", boiler / 8.0, 0.0, boiler, 2.0, boiler - 2.0),
        "hp": DailyEnergy(day, "hp", hp / 3.5, hp / 3.5, hp, 0.0, hp),
    }
    return DailyRecord(
        date=day,
        site_id="s",
        dd={"pbl": dd},
        heat_space_kwh=heat,
        heat_dhw_kwh=2.0,
        heat_by_generator=energies,
        flags=flags or set(),
    )


def test_forecast_hand_checked() -> None:
    # 40 days year to date: 20 kWh space heat per day at 10 degree days -> k = 2.0.
    records = [_record(SEASON.start + timedelta(days=i), 20.0, 10.0, 14.0, 8.0) for i in range(40)]
    clim = _climatology(dd_per_day=8.0)
    forecast = forecast_season(records, SEASON, clim, "pbl", dhw_per_day=2.0)
    assert forecast.heat_space_ytd == pytest.approx(800.0)
    assert forecast.dd_ytd == pytest.approx(400.0)
    assert forecast.k_ytd == pytest.approx(2.0)
    assert forecast.days_ytd == 40
    remaining_days = (SEASON.end - records[-1].date).days
    assert forecast.days_remaining == remaining_days == 172
    assert forecast.dd_remaining_clim == pytest.approx(8.0 * 172)
    assert forecast.heat_space_forecast == pytest.approx(800.0 + 2.0 * 8.0 * 172)
    assert forecast.heat_dhw_forecast == pytest.approx(40 * 2.0 + 2.0 * 172)
    assert forecast.heat_space_forecast_fit is None
    assert forecast.last_date == records[-1].date
    # Shares of the last 28 days: boiler 14 of 22, heat pump 8 of 22 of the total heat.
    remaining = 2.0 * 8.0 * 172 + 2.0 * 172
    assert forecast.per_generator["boiler"] == pytest.approx(40 * 14.0 + 14 / 22 * remaining)
    assert forecast.per_generator["hp"] == pytest.approx(40 * 8.0 + 8 / 22 * remaining)


def test_forecast_uses_only_usable_days_for_k_and_today() -> None:
    records = [_record(SEASON.start + timedelta(days=i), 20.0, 10.0, 14.0, 8.0) for i in range(40)]
    records[5] = _record(records[5].date, 500.0, 10.0, 14.0, 8.0, {Flag.PARTIAL_DAY})
    records[6] = _record(records[6].date, 0.0, 10.0, 0.0, 0.0, {Flag.ENERGY_MISSING})
    clim = _climatology(dd_per_day=8.0)
    forecast = forecast_season(
        records, SEASON, clim, "pbl", today=SEASON.start + timedelta(days=30)
    )
    assert forecast.days_ytd == 30
    assert forecast.k_ytd == pytest.approx(2.0)  # partial day excluded from k
    # The partial day counts in the year-to-date total, the missing day does not.
    assert forecast.heat_space_ytd == pytest.approx(28 * 20.0 + 500.0)
    assert forecast.days_remaining == (SEASON.end - (SEASON.start + timedelta(days=29))).days


def test_forecast_with_fit_variant_and_no_ytd_data() -> None:
    fit = SignatureFit(
        site_id="s",
        period=Period(date(2024, 10, 1), date(2025, 4, 30)),
        tac_preset="house",
        balance_temp=15.0,
        intercept_a=0.0,
        slope_b=2.0,
        wind_c=0.5,
        ua_w_per_k=83.3,
        r2=0.9,
        rmse=1.0,
        n_days=200,
        n_heating_days=180,
        ci95_slope=(1.9, 2.1),
        ci95_balance=(14.5, 15.5),
        fitted_at=datetime(2025, 5, 1, tzinfo=UTC),
    )
    clim = _climatology(dd_per_day=8.0, tac=5.0, wind=4.0)
    forecast = forecast_season([], SEASON, clim, "house", fit=fit)
    days = (SEASON.end - SEASON.start).days + 1
    # Without year-to-date data the model variant is the forecast: (2 x 10 + 0.5 x 4) per day.
    assert forecast.k_ytd is None and forecast.days_ytd == 0
    assert forecast.heat_space_forecast_fit == pytest.approx(22.0 * days)
    assert forecast.heat_space_forecast == pytest.approx(22.0 * days)
    # House degree days derived from the TAC climatology with the fitted balance temperature.
    assert forecast.dd_remaining_clim == pytest.approx(10.0 * days)
    assert forecast.per_generator == {}
    assert forecast.last_date is None


def test_generator_shares_and_carrier_amounts() -> None:
    records = [_record(SEASON.start + timedelta(days=i), 20.0, 10.0, 14.0, 8.0) for i in range(5)]
    shares = generator_shares_last_days(records, days=28)
    assert shares["boiler"] == pytest.approx(14 / 22) and shares["hp"] == pytest.approx(8 / 22)
    assert generator_shares_last_days([]) == {}
    site = Site(
        id="s",
        generators=[
            Generator.for_kind("boiler", "CV", GeneratorKind.GAS_BOILER),
            Generator.for_kind("hp", "WP", GeneratorKind.HEAT_PUMP, role=Role.SPACE),
        ],
    )
    forecast = forecast_season(records, SEASON, _climatology(8.0), "pbl")
    amounts = forecast_carrier_amounts(forecast, site)
    assert amounts["boiler"] == pytest.approx(forecast.per_generator["boiler"] / (8.792 * 0.95))
    assert amounts["hp"] == pytest.approx(forecast.per_generator["hp"] / 3.5)
