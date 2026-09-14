"""External statistic ids (ADR 0003). Home Assistant-free so tests can import it.

Keep the key strings in lockstep with ``const.py`` / ``statistics_writer.py``.
"""

from __future__ import annotations

from collections.abc import Iterable

DOMAIN = "heatprint"

METRIC_T_MEAN = "t_mean"
METRIC_TAC_PBL = "tac_pbl"
METRIC_TAC_HOUSE = "tac_house"
METRIC_DD_CLASSIC = "dd_classic"
METRIC_DD_KNMI14 = "dd_knmi14"
METRIC_DD_PBL = "dd_pbl"
METRIC_DD_HOUSE = "dd_house"
METRIC_HEAT_SPACE = "heat_space"
METRIC_HEAT_DHW = "heat_dhw"
METRIC_ELECTRIC_HP = "electric_hp"
METRIC_GAS = "gas"
METRIC_HEAT_UNALLOCATED = "heat_unallocated"
METRIC_COST = "cost"
METRIC_CO2 = "co2"

SITE_SUM_METRICS: tuple[str, ...] = (
    METRIC_DD_CLASSIC,
    METRIC_DD_KNMI14,
    METRIC_DD_PBL,
    METRIC_DD_HOUSE,
    METRIC_HEAT_SPACE,
    METRIC_HEAT_DHW,
    METRIC_HEAT_UNALLOCATED,
    METRIC_GAS,
    METRIC_ELECTRIC_HP,
    METRIC_COST,
    METRIC_CO2,
)
SITE_MEAN_METRICS: tuple[str, ...] = (METRIC_T_MEAN, METRIC_TAC_PBL, METRIC_TAC_HOUSE)


def statistic_id(site_id: str, metric: str) -> str:
    """Return the external statistic id for a site metric: heatprint:<site>_<metric>."""
    return f"{DOMAIN}:{site_id}_{metric}"


def generator_metric(generator_id: str) -> str:
    """Return the metric key for the space heat delivered by one generator."""
    return f"heat_{generator_id}"


def generator_dhw_metric(generator_id: str) -> str:
    """Return the metric key for the DHW heat delivered by one generator."""
    return f"heat_dhw_{generator_id}"


def room_heat_metric(room_id: str) -> str:
    """Return the metric key for allocated space heat of one room."""
    return f"room_{room_id}_heat"


def room_demand_metric(room_id: str) -> str:
    """Return the metric key for the daily demand integral of one room."""
    return f"room_{room_id}_demand"


def room_t_mean_metric(room_id: str) -> str:
    """Return the metric key for the daily mean room temperature."""
    return f"room_{room_id}_t_mean"


def room_cost_metric(room_id: str) -> str:
    """Return the metric key for allocated space-heating cost of one room."""
    return f"room_{room_id}_cost"


def generator_clear_statistic_ids(site_id: str, generator_id: str) -> list[str]:
    """Statistic ids removed when clearing one generator."""
    return [
        statistic_id(site_id, generator_metric(generator_id)),
        statistic_id(site_id, generator_dhw_metric(generator_id)),
    ]


def site_clear_statistic_ids(
    site_id: str,
    *,
    generator_ids: Iterable[str],
    dhw_generator_ids: Iterable[str] = (),
    room_ids: Iterable[str] = (),
) -> list[str]:
    """All Heatprint statistic ids of a site, including room demand / t_mean means."""
    ids = [statistic_id(site_id, metric) for metric in (*SITE_SUM_METRICS, *SITE_MEAN_METRICS)]
    seen = set(ids)
    for generator_id in generator_ids:
        for key in (generator_metric(generator_id),):
            sid = statistic_id(site_id, key)
            if sid not in seen:
                ids.append(sid)
                seen.add(sid)
    for generator_id in dhw_generator_ids:
        sid = statistic_id(site_id, generator_dhw_metric(generator_id))
        if sid not in seen:
            ids.append(sid)
            seen.add(sid)
    for room_id in room_ids:
        for key in (
            room_heat_metric(room_id),
            room_cost_metric(room_id),
            room_demand_metric(room_id),
            room_t_mean_metric(room_id),
        ):
            sid = statistic_id(site_id, key)
            if sid not in seen:
                ids.append(sid)
                seen.add(sid)
    return ids
