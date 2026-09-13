"""Write Heatprint day records as external long-term statistics (ADR 0003).

One row per day at 00:00 local time. Mean metrics carry the day value as ``mean``
(and min/max equal to it); sum metrics carry the running total in ``sum`` and
``state`` so the statistics graph card shows the day value in "change" mode.
Writing the same ``start`` again overwrites the row, which makes recomputation
idempotent as long as a rewritten window always extends to the newest day.

Handles both the pre-2025.4 ``has_mean`` metadata and the newer ``mean_type`` /
``unit_class`` fields by inspecting ``StatisticMetaData`` at import time.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import datetime, tzinfo
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    METRIC_HEAT_DHW_GENERATOR_PREFIX,
    METRIC_HEAT_GENERATOR_PREFIX,
    SITE_METRICS,
    STATISTIC_MEAN,
    STATISTIC_SUM,
    MetricDef,
    generator_dhw_metric,
    generator_metric,
    statistic_id,
)
from .core_api import DayMetrics, GeneratorConfig
from .recorder_source import async_last_sum_before

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # Home Assistant < 2025.4
    StatisticMeanType = None  # type: ignore[assignment,misc]

_META_FIELDS: frozenset[str] = frozenset(getattr(StatisticMetaData, "__annotations__", {}))
_SUPPORTS_MEAN_TYPE = StatisticMeanType is not None and "mean_type" in _META_FIELDS
_SUPPORTS_UNIT_CLASS = "unit_class" in _META_FIELDS

METRIC_NAMES: dict[str, str] = {
    "t_mean": "Mean temperature",
    "tac_pbl": "Effective temperature (PBL)",
    "tac_house": "Effective temperature (house)",
    "dd_classic": "Degree days (classic)",
    "dd_knmi14": "Degree days (KNMI 14 °C)",
    "dd_pbl": "Degree days (PBL)",
    "dd_house": "Degree days (house)",
    "heat_space": "Space heating",
    "heat_dhw": "Hot water and cooking",
    "electric_hp": "Heat pump electricity",
    "gas": "Gas",
}


def metric_definitions(generators: Iterable[GeneratorConfig]) -> dict[str, MetricDef]:
    """Return all metric definitions for a site including the per-generator metrics."""
    definitions = {metric.key: metric for metric in SITE_METRICS}
    for generator in generators:
        definitions[generator_metric(generator.generator_id)] = MetricDef(
            generator_metric(generator.generator_id),
            STATISTIC_SUM,
            UnitOfEnergy.KILO_WATT_HOUR,
            "energy",
        )
        definitions[generator_dhw_metric(generator.generator_id)] = MetricDef(
            generator_dhw_metric(generator.generator_id),
            STATISTIC_SUM,
            UnitOfEnergy.KILO_WATT_HOUR,
            "energy",
        )
    return definitions


def _metric_name(site_name: str, metric: MetricDef, generators: Mapping[str, str]) -> str:
    """Return a human readable name for the statistic."""
    if metric.key.startswith(METRIC_HEAT_DHW_GENERATOR_PREFIX):
        generator_id = metric.key[len(METRIC_HEAT_DHW_GENERATOR_PREFIX) :]
        if generator_id in generators:
            return f"{site_name} {generators[generator_id]} hot water"
    if metric.key.startswith(METRIC_HEAT_GENERATOR_PREFIX):
        generator_id = metric.key[len(METRIC_HEAT_GENERATOR_PREFIX) :]
        if generator_id in generators:
            return f"{site_name} {generators[generator_id]} space heating"
    return f"{site_name} {METRIC_NAMES.get(metric.key, metric.key)}"


@callback
def build_metadata(site_id: str, name: str, metric: MetricDef) -> StatisticMetaData:
    """Build StatisticMetaData compatible with the running Home Assistant version."""
    metadata: dict[str, Any] = {
        "source": DOMAIN,
        "statistic_id": statistic_id(site_id, metric.key),
        "name": name,
        "unit_of_measurement": metric.unit,
        "has_sum": metric.kind == STATISTIC_SUM,
    }
    is_mean = metric.kind == STATISTIC_MEAN
    if _SUPPORTS_MEAN_TYPE:
        metadata["mean_type"] = (
            StatisticMeanType.ARITHMETIC if is_mean else StatisticMeanType.NONE  # type: ignore[union-attr]
        )
    else:
        metadata["has_mean"] = is_mean
    if _SUPPORTS_UNIT_CLASS:
        metadata["unit_class"] = metric.unit_class
    return metadata  # type: ignore[return-value]


def _local_midnight(day: Any, tz: tzinfo) -> datetime:
    """Return local midnight (tz-aware) for a date; the recorder converts to UTC."""
    return datetime.combine(day, datetime.min.time(), tzinfo=tz)


async def async_write_daily_metrics(
    hass: HomeAssistant,
    site_id: str,
    site_name: str,
    records: Iterable[DayMetrics],
    generators: Iterable[GeneratorConfig],
    tz: tzinfo,
    sum_offsets: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Upsert the day metrics of ``records`` as external statistics.

    ``sum_offsets`` carries the running totals across chunks of a backfill; when
    a metric is missing there the total continues from the last row stored before
    the first record. Returns the running totals after this batch so the caller
    can pass them into the next chunk.
    """
    generator_list = list(generators)
    rows = sorted(records, key=lambda item: item.date)
    if not rows:
        return dict(sum_offsets or {})
    definitions = metric_definitions(generator_list)
    generator_names = {generator.generator_id: generator.name for generator in generator_list}
    running: dict[str, float] = dict(sum_offsets or {})
    first_day = rows[0].date

    present_metrics = {key for row in rows for key, value in row.values.items() if value is not None}
    for key in sorted(present_metrics):
        metric = definitions.get(key)
        if metric is None:
            _LOGGER.debug("Skipping unknown metric %s", key)
            continue
        sid = statistic_id(site_id, key)
        stats: list[StatisticData] = []
        if metric.kind == STATISTIC_SUM:
            if key not in running:
                previous = await async_last_sum_before(hass, sid, first_day, tz)
                running[key] = previous or 0.0
            total = running[key]
            for row in rows:
                value = row.values.get(key)
                if value is None:
                    continue
                total += float(value)
                stats.append(
                    StatisticData(start=_local_midnight(row.date, tz), state=total, sum=total)
                )
            running[key] = total
        else:
            for row in rows:
                value = row.values.get(key)
                if value is None:
                    continue
                stats.append(
                    StatisticData(
                        start=_local_midnight(row.date, tz),
                        mean=float(value),
                        min=float(value),
                        max=float(value),
                    )
                )
        if not stats:
            continue
        metadata = build_metadata(site_id, _metric_name(site_name, metric, generator_names), metric)
        async_add_external_statistics(hass, metadata, stats)
    return running


async def async_clear_statistics(hass: HomeAssistant, statistic_ids: Iterable[str]) -> None:
    """Delete external statistics (used when a generator is removed on request)."""
    ids = [sid for sid in statistic_ids if sid]
    if not ids:
        return
    instance = get_instance(hass)
    await instance.async_add_executor_job(clear_statistics, instance, ids)
