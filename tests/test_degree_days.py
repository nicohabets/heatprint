"""Degree-day methods (METHODS section 4)."""

from __future__ import annotations

from datetime import date

import pytest

from heatprint_core.flags import Flag
from heatprint_core.methods.degree_days import (
    compute_all,
    compute_day,
    dd_classic,
    dd_house,
    dd_knmi14,
    dd_pbl,
)
from heatprint_core.methods.pbl_params import PBL_OPTIMAL, PBL_PRACTICAL, pbl_params
from heatprint_core.models import ClassicParams, DailyWeather, MethodConfig, PblParams


def test_classic_with_mindergas_weights() -> None:
    # January: (18 - 5) x 1.1
    assert dd_classic(5.0, 1) == (pytest.approx(14.3), 13.0)
    # April: (18 - 10) x 0.8
    assert dd_classic(10.0, 4) == (pytest.approx(6.4), 8.0)
    # October: weight 1.0
    assert dd_classic(12.0, 10) == (6.0, 6.0)


def test_classic_heating_limit_and_unweighted() -> None:
    params = ClassicParams(base_temp=18.0, heating_limit=15.5)
    assert dd_classic(16.0, 1, params) == (0.0, 0.0)  # above the heating limit
    assert dd_classic(15.0, 1, params) == (pytest.approx(3.3), 3.0)
    unweighted = ClassicParams(weighted=False)
    assert dd_classic(5.0, 1, unweighted) == (13.0, 13.0)
    assert dd_classic(18.0, 1) == (0.0, 0.0)
    assert dd_classic(25.0, 7) == (0.0, 0.0)


def test_knmi14() -> None:
    assert dd_knmi14(3.0) == 11.0
    assert dd_knmi14(14.0) == 0.0
    assert dd_knmi14(20.0) == 0.0


def test_pbl_month_parameters() -> None:
    assert pbl_params(1) == PBL_PRACTICAL[0]
    assert pbl_params(12).tst == 17.01 and pbl_params(2).rer == 1.00
    assert pbl_params(3).tst == 15.26 and pbl_params(11).rer == 1.02
    assert pbl_params(4).tst == 15.10 and pbl_params(10).rer == 0.79
    for month in range(5, 10):
        assert pbl_params(month).tst == 13.92 and pbl_params(month).rer == 0.61
    assert pbl_params(1).top == 1.30
    assert pbl_params(1, "optimal") == PBL_OPTIMAL[0]
    assert pbl_params(6, "optimal").tst == 15.15 and pbl_params(6, "optimal").rer == 0.73
    assert pbl_params(6, "optimal").top == 1.32
    with pytest.raises(ValueError):
        pbl_params(13)
    with pytest.raises(ValueError):
        pbl_params(1, "fantasy")


def test_pbl_degree_days_per_month_group() -> None:
    assert dd_pbl(5.0, 1) == pytest.approx(1.00 * (17.01 - 5.0))  # 12.01
    assert dd_pbl(5.0, 3) == pytest.approx(1.02 * (15.26 - 5.0))
    assert dd_pbl(5.0, 10) == pytest.approx(0.79 * (15.10 - 5.0))
    assert dd_pbl(5.0, 7) == pytest.approx(0.61 * (13.92 - 5.0))
    assert dd_pbl(18.0, 1) == 0.0
    assert dd_pbl(5.0, 1, PblParams(include_top=True)) == pytest.approx(12.01 + 1.30)
    assert dd_pbl(5.0, 1, PblParams(parameter_set="optimal")) == pytest.approx(14.91 - 5.0)


def test_house() -> None:
    assert dd_house(3.6, 15.0) == pytest.approx(11.4)
    assert dd_house(16.0, 15.0) == 0.0


def test_compute_all_with_history_and_fit() -> None:
    yesterday = DailyWeather(date(2026, 1, 9), t_mean=1.0, wind_mean=2.0, radiation=100.0)
    today = DailyWeather(date(2026, 1, 10), t_mean=5.0, wind_mean=3.0, radiation=180.0)
    values = compute_all(today, yesterday, MethodConfig(), house_balance_temp=15.0)
    assert values["t_eff_knmi"] == pytest.approx(3.0)
    tac_pbl = 0.65 * (5.0 - 3.0 / 1.5) + 0.35 * (1.0 - 2.0 / 1.5)
    assert values["tac_pbl"] == pytest.approx(tac_pbl)
    assert values["tac_house"] == pytest.approx(0.65 * 5.0 + 0.35 * 1.0)
    assert values["classic"] == pytest.approx(14.3)
    assert values["classic_unweighted"] == 13.0
    assert values["knmi14"] == pytest.approx(11.0)
    assert values["pbl"] == pytest.approx(17.01 - tac_pbl)
    assert values["house"] == pytest.approx(15.0 - 3.6)


def test_compute_day_fallbacks_and_flags() -> None:
    today = DailyWeather(date(2026, 1, 10), t_mean=5.0, wind_mean=3.0)
    result = compute_day(today, None, MethodConfig(), house_balance_temp=None)
    # First day: TAC = T_eff, house falls back to 15.5 on the PBL TAC.
    assert result.tac_pbl == pytest.approx(3.0)
    assert result.dd["house"] == pytest.approx(15.5 - 3.0)
    assert Flag.WEATHER_PARTIAL in result.flags
    assert Flag.HOUSE_NOT_FITTED in result.flags

    no_wind = DailyWeather(date(2026, 1, 10), t_mean=5.0, wind_mean=None)
    result = compute_day(
        no_wind, DailyWeather(date(2026, 1, 9), 5.0, None), house_balance_temp=15.0
    )
    assert Flag.WEATHER_PARTIAL in result.flags
    assert Flag.HOUSE_NOT_FITTED not in result.flags
    assert result.t_eff_knmi == 5.0


def test_classic_with_effective_temperature_reference() -> None:
    today = DailyWeather(date(2026, 1, 10), t_mean=5.0, wind_mean=3.0)
    config = MethodConfig(classic=ClassicParams(t_ref="knmi"))
    values = compute_all(today, None, config)
    assert values["classic_unweighted"] == pytest.approx(18.0 - 3.0)
