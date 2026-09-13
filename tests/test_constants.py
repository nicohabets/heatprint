"""Constants and station table (METHODS section 1)."""

from __future__ import annotations

import pytest

from heatprint_core import constants
from heatprint_core.constants import (
    KNMI_STATIONS,
    MONTH_WEIGHTS,
    haversine_km,
    nearest_station,
)


def test_conversion_constants() -> None:
    assert constants.GAS_HS_KWH_PER_M3 == 8.792
    assert constants.GAS_HI_KWH_PER_M3 == 7.92
    assert constants.GJ_TO_KWH == 277.78
    assert constants.MJ_M2_TO_J_CM2 == 100.0
    assert constants.WH_M2_TO_J_CM2 == 0.36
    assert pytest.approx(1 / 3.6) == constants.KMH_TO_MS
    assert constants.KNMI_TENTHS == 0.1
    assert constants.GAS_CO2_KG_PER_M3 == 1.78
    assert constants.ELEC_CO2_KG_PER_KWH == 0.30
    assert pytest.approx(41.6667, abs=1e-3) == constants.W_PER_K_FROM_KWH_PER_K_DAY
    assert constants.PBL_WIND_SQRT_COEF == 1.0
    assert pytest.approx(1 / 480) == constants.PBL_SUN_COEF


def test_month_weights_mindergas() -> None:
    assert [MONTH_WEIGHTS[m] for m in (11, 12, 1, 2)] == [1.1] * 4
    assert MONTH_WEIGHTS[3] == 1.0 and MONTH_WEIGHTS[10] == 1.0
    assert all(MONTH_WEIGHTS[m] == 0.8 for m in range(4, 10))
    assert len(MONTH_WEIGHTS) == 12


def test_station_table() -> None:
    assert len(KNMI_STATIONS) >= 35
    name, lat, lon = KNMI_STATIONS[380]
    assert name == "Maastricht"
    assert 50.8 < lat < 51.0 and 5.6 < lon < 5.9
    assert KNMI_STATIONS[260][0] == "De Bilt"


def test_haversine_known_distance() -> None:
    # De Bilt to Maastricht is roughly 138 km.
    distance = haversine_km(52.10, 5.18, 50.91, 5.76)
    assert 130 < distance < 145


def test_nearest_station_heerlen() -> None:
    ranked = nearest_station(50.89, 5.98)
    assert ranked[0][0] == 380
    assert ranked[0][1] == "Maastricht"
    assert ranked[0][2] < 20
    assert [r[2] for r in ranked] == sorted(r[2] for r in ranked)
    assert len(ranked) == len(KNMI_STATIONS)
