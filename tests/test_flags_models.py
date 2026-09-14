"""Flags (METHODS section 10) and model (de)serialisation (DATA_MODEL)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from heatprint_core.flags import (
    EXCLUSION_FLAGS,
    Flag,
    flags_from_bitmask,
    flags_to_bitmask,
    is_usable,
    parse_flags,
)
from heatprint_core.models import (
    CarrierUnit,
    Climatology,
    Conversion,
    ConversionMode,
    DhwMode,
    Forecast,
    Generator,
    GeneratorKind,
    HouseParams,
    Measure,
    MeasureCategory,
    MethodConfig,
    Period,
    PriceMode,
    Role,
    Season,
    SignatureFit,
    Site,
    default_conversion,
)


def test_flag_values_and_exclusion() -> None:
    assert len(Flag) == 18
    assert Flag.DHW_BASELINE_MISSING.value == "dhw_baseline_missing"
    assert Flag.ROOM_DEMAND_MISSING.value == "room_demand_missing"
    assert Flag.ROOM_NOT_FITTED.value == "room_not_fitted"
    assert Flag.PRICE_ESTIMATED_FLAT.value == "price_estimated_flat"
    assert Flag.WEATHER_MISSING.value == "weather_missing"
    assert Flag("outlier") is Flag.OUTLIER
    assert {
        Flag.WEATHER_MISSING,
        Flag.ENERGY_MISSING,
        Flag.PARTIAL_DAY,
        Flag.METER_RESET,
        Flag.OUTLIER,
    } == EXCLUSION_FLAGS
    assert Flag.DHW_BASELINE_MISSING not in EXCLUSION_FLAGS
    assert is_usable({Flag.WEATHER_PARTIAL, Flag.HEAT_ESTIMATED, Flag.INTERPOLATED})
    assert is_usable({Flag.DHW_BASELINE_MISSING})
    assert not is_usable({Flag.PARTIAL_DAY})


def test_bitmask_round_trip() -> None:
    flags = {Flag.WEATHER_MISSING, Flag.OUTLIER, Flag.IMPORTED}
    mask = flags_to_bitmask(flags)
    assert mask == (1 << 0) | (1 << 9) | (1 << 10)
    assert flags_from_bitmask(mask) == flags
    assert flags_from_bitmask(0) == set()
    assert list(Flag).index(Flag.DHW_BASELINE_MISSING) == 11
    assert flags_to_bitmask({Flag.DHW_BASELINE_MISSING}) == 1 << 11
    assert flags_from_bitmask(1 << 11) == {Flag.DHW_BASELINE_MISSING}
    assert list(Flag).index(Flag.PRICE_ESTIMATED_FLAT) == 17
    assert flags_to_bitmask({Flag.PRICE_ESTIMATED_FLAT}) == 1 << 17


def test_parse_flags_case_insensitive() -> None:
    assert parse_flags(["WEATHER_MISSING", "outlier", Flag.IMPORTED]) == {
        Flag.WEATHER_MISSING,
        Flag.OUTLIER,
        Flag.IMPORTED,
    }


def test_defaults_follow_docs() -> None:
    conversion = Conversion()
    assert conversion.efficiency == 0.95
    assert conversion.heating_value == 8.792
    assert conversion.scop == 3.5
    assert conversion.cop == 3.0
    methods = MethodConfig()
    assert methods.classic.base_temp == 18.0
    assert methods.classic.heating_limit == 18.0
    assert methods.classic.weighted is True
    assert methods.pbl.wind_mode == "linear"
    assert methods.pbl.include_sun is False
    assert methods.pbl.include_top is False
    assert methods.house.tac_weights == (0.65, 0.35)
    assert methods.primary == "house"
    assert methods.enabled == ["classic", "pbl", "house"]
    assert HouseParams().fit_wind is True
    site = Site(id="home")
    assert site.season.start_month == 10 and site.season.start_day == 1
    assert site.backfill_years == 3 and site.climatology_years == 20
    assert default_conversion(GeneratorKind.DISTRICT_HEAT).efficiency == 1.0


def test_generator_for_kind_defaults() -> None:
    boiler = Generator.for_kind("boiler", "Gas boiler", GeneratorKind.GAS_BOILER)
    assert boiler.carrier.unit is CarrierUnit.M3
    assert boiler.conversion.mode is ConversionMode.FIXED_EFFICIENCY
    assert boiler.role is Role.BOTH
    assert boiler.dhw.mode is DhwMode.BASELINE
    heat_pump = Generator.for_kind("hp", "HP", GeneratorKind.HEAT_PUMP, role=Role.SPACE)
    assert heat_pump.conversion.mode is ConversionMode.COP_FIXED
    assert heat_pump.is_heat_pump
    assert not boiler.is_heat_pump
    assert boiler.price_mode is PriceMode.FLAT
    dynamic = Generator.for_kind(
        "hp2", "HP2", GeneratorKind.HEAT_PUMP, role=Role.SPACE, price_mode=PriceMode.DYNAMIC
    )
    assert dynamic.to_dict()["price_mode"] == "dynamic"
    assert Generator.from_dict(dynamic.to_dict()).price_mode is PriceMode.DYNAMIC


def test_site_json_round_trip() -> None:
    site = Site(
        id="home",
        name="Home",
        latitude=50.89,
        longitude=5.98,
        generators=[
            Generator.for_kind("boiler", "Boiler", GeneratorKind.GAS_BOILER),
            Generator.for_kind("hp", "HP", GeneratorKind.HEAT_PUMP, role=Role.SPACE),
        ],
        measures=[Measure("m1", "Triple glazing", date(2025, 6, 1), MeasureCategory.INSULATION)],
    )
    payload = json.loads(json.dumps(site.to_dict()))
    restored = Site.from_dict(payload)
    assert restored == site
    assert payload["generators"][0]["kind"] == "gas_boiler"
    assert payload["measures"][0]["date"] == "2025-06-01"
    assert payload["methods"]["house"]["tac_weights"] == [0.65, 0.35]


def test_fit_and_forecast_round_trip() -> None:
    fit = SignatureFit(
        site_id="home",
        period=Period(date(2025, 10, 1), date(2026, 4, 30), label="2025/26"),
        tac_preset="house",
        balance_temp=15.0,
        intercept_a=1.0,
        slope_b=2.5,
        wind_c=0.4,
        ua_w_per_k=104.17,
        r2=0.95,
        rmse=1.9,
        n_days=180,
        n_heating_days=160,
        ci95_slope=(2.4, 2.6),
        ci95_balance=(14.5, 15.5),
        fitted_at=datetime(2026, 5, 1, 6, 15, tzinfo=UTC),
        outliers=[date(2026, 1, 15)],
    )
    payload = json.loads(json.dumps(fit.to_dict()))
    assert SignatureFit.from_dict(payload) == fit
    assert fit.predict(10.0, 5.0) == 1.0 + 2.5 * 5.0 + 0.4 * 5.0

    forecast = Forecast(
        season=Season("2025/26", date(2025, 10, 1), date(2026, 9, 30)),
        method="pbl",
        heat_space_ytd=1500.0,
        dd_ytd=900.0,
        dd_remaining_clim=1200.0,
        heat_space_forecast=3500.0,
        per_generator={"boiler": 3000.0, "hp": 500.0},
        k_ytd=1.667,
        last_date=date(2026, 1, 31),
    )
    payload = json.loads(json.dumps(forecast.to_dict()))
    assert Forecast.from_dict(payload) == forecast


def test_climatology_round_trip() -> None:
    clim = Climatology(
        site_id="home",
        years=20,
        tac_by_doy=[None] + [5.0] * 365,
        wind_by_doy=[4.0] * 366,
        dd_by_doy={"pbl": [10.0] * 366},
        computed_at=date(2026, 9, 1),
    )
    payload = json.loads(json.dumps(clim.to_dict()))
    assert Climatology.from_dict(payload) == clim


def test_daily_record_round_trip() -> None:
    from heatprint_core.models import DailyEnergy, DailyRecord

    record = DailyRecord(
        date=date(2026, 1, 10),
        site_id="home",
        t_mean=3.5,
        wind_mean=4.2,
        tac_house=3.0,
        dd={"classic": 15.95, "pbl": 14.0},
        heat_space_kwh=30.0,
        cost_eur=8.0,
        cost_space_eur=7.2,
        heat_by_generator={
            "boiler": DailyEnergy(date(2026, 1, 10), "boiler", 4.0, 0.0, 33.4, 3.4, 30.0)
        },
        flags={Flag.WEATHER_PARTIAL, Flag.HEAT_ESTIMATED},
    )
    payload = json.loads(json.dumps(record.to_dict()))
    assert payload["flags"] == ["heat_estimated", "weather_partial"]
    assert DailyRecord.from_dict(payload) == record
