"""HA-free statistic id helpers used by clear_statistics."""

from __future__ import annotations

from metric_ids import (
    generator_clear_statistic_ids,
    room_cost_metric,
    room_demand_metric,
    room_heat_metric,
    room_t_mean_metric,
    site_clear_statistic_ids,
    statistic_id,
)


def test_room_mean_metric_keys() -> None:
    assert room_heat_metric("living") == "room_living_heat"
    assert room_demand_metric("living") == "room_living_demand"
    assert room_t_mean_metric("living") == "room_living_t_mean"
    assert room_cost_metric("living") == "room_living_cost"


def test_generator_clear_ids() -> None:
    ids = generator_clear_statistic_ids("home", "boiler")
    assert ids == [
        "heatprint:home_heat_boiler",
        "heatprint:home_heat_dhw_boiler",
    ]


def test_site_clear_ids_include_room_demand_and_t_mean() -> None:
    ids = site_clear_statistic_ids(
        "home",
        generator_ids=["boiler"],
        dhw_generator_ids=["boiler"],
        room_ids=["living", "bath"],
    )
    assert statistic_id("home", "t_mean") in ids
    assert statistic_id("home", "heat_space") in ids
    assert statistic_id("home", "heat_unallocated") in ids
    assert statistic_id("home", "cost") in ids
    assert statistic_id("home", "co2") in ids
    assert "heatprint:home_heat_boiler" in ids
    assert "heatprint:home_heat_dhw_boiler" in ids
    assert "heatprint:home_room_living_heat" in ids
    assert "heatprint:home_room_living_cost" in ids
    assert "heatprint:home_room_living_demand" in ids
    assert "heatprint:home_room_living_t_mean" in ids
    assert "heatprint:home_room_bath_demand" in ids
    assert "heatprint:home_room_bath_t_mean" in ids
    # Site clear must not drop the room means that the previous implementation skipped.
    means = [sid for sid in ids if sid.endswith("_demand") or sid.endswith("_t_mean")]
    assert "heatprint:home_room_living_demand" in means
    assert "heatprint:home_t_mean" in ids
