"""Coordinator for Heatprint: daily processing, backfill, recompute, snapshot.

Runs the pipeline (ARCHITECTURE 4) once a day at 06:15 local time and on first
setup: fetch weather, read energy from the recorder, build day records with the
core, write them as external statistics, refresh the store and publish a
``HeatprintData`` snapshot for the entities. The backfill and a recompute run
the same pipeline over a longer range in chunks of 90 days as background tasks.
Analyses (fit, comparison, forecast) rebuild the core day records of the period
they need from the weather cache/provider and the recorder.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BACKFILL_CHUNK_DAYS,
    CONF_BACKFILL_YEARS,
    CONF_CLIMATOLOGY_YEARS,
    CONF_CO2_ENTITY,
    CONF_HA_ENTITIES,
    CONF_HOUSE_FIT_WIND,
    CONF_IMPORT_NOW,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_METHODS_PRIMARY,
    CONF_MIN_FIT_DAYS,
    CONF_MINDERGAS_DAILY_PUSH,
    CONF_MINDERGAS_GENERATOR,
    CONF_MINDERGAS_TOKEN,
    CONF_NAME,
    CONF_OUTLIER_THRESHOLD,
    CONF_PROVIDER,
    CONF_RECOMPUTE_FROM,
    CONF_ROOMS_ALLOCATION,
    CONF_ROOMS_MIN_FIT_DAYS,
    CONF_SITE_ID,
    CONF_TIMEZONE,
    CONF_WEATHER,
    DAILY_RUN_TIME,
    DATA_QUALITY_WINDOW_DAYS,
    DHW_BASELINE,
    DHW_MEASURED,
    DOMAIN,
    EXCLUSION_FLAGS,
    FALLBACK_METHOD_PRIMARY,
    FIT_REFRESH_DAYS,
    METHOD_HOUSE,
    METHOD_TO_DD_METRIC,
    METRIC_CO2,
    METRIC_COST,
    METRIC_ELECTRIC_HP,
    METRIC_GAS,
    METRIC_HEAT_DHW,
    METRIC_HEAT_SPACE,
    METRIC_HEAT_UNALLOCATED,
    METRIC_T_MEAN,
    METRIC_TAC_HOUSE,
    METRIC_TAC_PBL,
    NOTIFICATION_BACKFILL,
    NOTIFICATION_IMPORT_HINT,
    OPT_INTEGRATIONS,
    OPT_PRICING,
    PRICE_MODE_DYNAMIC,
    PROVIDER_HA_SENSORS,
    ROLE_BOTH,
    ROLE_DHW,
    WEATHER_CACHE_DAYS,
    generator_dhw_metric,
    generator_metric,
    room_cost_metric,
    room_heat_metric,
    statistic_id,
)
from .core_api import (
    CoreError,
    DailyEnergyInput,
    DayMetrics,
    GeneratorConfig,
    InsufficientData,
    MeasureConfig,
    RoomConfig,
    SeasonWindow,
    WeatherDay,
    advanced_options,
    allocate_rooms,
    apply_room_not_fitted,
    async_fetch_weather,
    baselines_in_kwh,
    build_climatology,
    build_daily_records,
    build_site_from_entry,
    compare_periods,
    daily_consumption_from_readings,
    effective_co2_factors,
    estimate_baselines,
    fit_room_signature,
    fit_signature,
    forecast_season,
    generator_configs,
    history_options,
    measure_configs,
    measure_effect,
    merge_room_metrics,
    method_options,
    output_w_per_m2_table,
    pricing_options,
    record_flags,
    record_is_usable,
    record_to_metrics,
    room_configs,
    rooms_options,
    season_for,
    weather_from_ha_sensors,
    weather_signature,
)
from .history_values import demand_requires_history
from .issues import async_clear_weather_check_failed
from .metric_ids import generator_clear_statistic_ids, site_clear_statistic_ids
from .mindergas import MindergasError, async_push_reading
from .recorder_source import (
    async_daily_from_history,
    async_daily_means,
    async_daily_metrics,
    async_daily_sums,
    async_hourly_changes,
    async_hourly_means,
    async_meter_reading_at,
)
from .statistics_writer import async_clear_statistics, async_write_daily_metrics
from .store import (
    META_BACKFILL_DONE,
    META_CLIMATOLOGY_SIGNATURE,
    META_LAST_DEFINITIVE_DATE,
    META_LAST_FIT_AT,
    META_LAST_ROOM_FIT_AT,
    META_LAST_RUN,
    META_RECOMPUTE_MARKER,
    META_WEATHER_SIGNATURE,
    HeatprintStore,
)

_LOGGER = logging.getLogger(__name__)

META_BASELINES_AT = "baselines_at"
BASELINE_REFRESH_DAYS = 30
INITIAL_WINDOW_DAYS = 7


# --------------------------------------------------------------------------------
# Snapshot dataclasses (what the entities read)
# --------------------------------------------------------------------------------


@dataclass(slots=True)
class GeneratorAggregate:
    """Season totals of one generator."""

    generator_id: str
    name: str
    kind: str
    heat_space_kwh: float = 0.0
    heat_dhw_kwh: float = 0.0
    share: float | None = None
    cost_eur: float | None = None
    electric_kwh: float = 0.0
    avg_price_paid: float | None = None
    price_mode: str = "flat"


@dataclass(slots=True)
class RoomAggregate:
    """Season totals and latest fit of one room."""

    room_id: str
    name: str
    heat_kwh: float = 0.0
    share: float | None = None
    heat_yesterday_kwh: float | None = None
    cost_eur: float | None = None
    cost_yesterday_eur: float | None = None
    cost_per_m2: float | None = None
    heat_per_m2: float | None = None
    floor_area_m2: float | None = None
    ua_w_per_k: float | None = None
    ua_w_per_k_per_m2: float | None = None
    ua_indicative_w_per_k: float | None = None
    balance_temp: float | None = None
    fit: dict[str, Any] | None = None
    flags: list[str] = field(default_factory=list)
    data_quality: float | None = None


@dataclass(slots=True)
class SeasonAggregate:
    """Season-to-date totals (from the site's own external statistics)."""

    label: str
    start: date
    end: date
    days: int = 0
    dd: dict[str, float] = field(default_factory=dict)
    heat_space_kwh: float = 0.0
    heat_dhw_kwh: float = 0.0
    gas_m3: float = 0.0
    electric_hp_kwh: float = 0.0
    share_heat_pump: float | None = None
    heat_per_dd: dict[str, float] = field(default_factory=dict)
    gas_per_dd_classic: float | None = None
    per_generator: dict[str, GeneratorAggregate] = field(default_factory=dict)
    heat_unallocated_kwh: float = 0.0
    cost_eur: float = 0.0
    cost_space_eur: float = 0.0
    co2_kg: float = 0.0
    per_room: dict[str, RoomAggregate] = field(default_factory=dict)
    most_expensive_room: str | None = None
    room_ranked_by: str = "heat_kwh"
    room_ranking: list[dict[str, Any]] = field(default_factory=list)
    room_ranking_by_heat: list[dict[str, Any]] = field(default_factory=list)
    room_ranking_by_heat_loss: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class LatestDay:
    """The newest processed day record (usually yesterday)."""

    date: date
    t_mean: float | None
    tac_primary: float | None
    dd: dict[str, float]
    heat_space_kwh: float | None
    heat_dhw_kwh: float | None
    cost_eur: float | None
    co2_kg: float | None
    cop: float | None
    flags: list[str]
    provisional: bool


@dataclass(slots=True)
class DataQuality:
    """Share of usable days in the last 30 days and the current gap."""

    usable_share: float | None
    flag_counts: dict[str, int]
    gap_days: int
    last_usable: date | None


@dataclass(slots=True)
class HeatprintData:
    """Snapshot published by the coordinator."""

    latest: LatestDay | None
    season: SeasonAggregate
    fit: dict[str, Any] | None
    forecast: dict[str, Any] | None
    dhw_baseline: dict[str, float]
    data_quality: DataQuality
    last_weather_update: datetime | None
    primary_method: str
    last_run: datetime
    room_fits: dict[str, dict[str, Any]] = field(default_factory=dict)


def _daterange(start: date, end: date) -> Iterable[date]:
    """Yield every date from start to end inclusive."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


class HeatprintCoordinator(DataUpdateCoordinator[HeatprintData]):
    """Orchestrates the daily pipeline for one site (config entry)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator; heavy work happens in _async_setup."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=None,
        )
        self.entry = entry
        self.store = HeatprintStore(hass, entry.entry_id)
        self.site_id: str = entry.data[CONF_SITE_ID]
        self.site_name: str = entry.data.get(CONF_NAME, entry.title)
        self.tz = (
            dt_util.get_time_zone(entry.data[CONF_TIMEZONE]) or dt_util.get_default_time_zone()
        )
        self.generators: list[GeneratorConfig] = generator_configs(entry)
        self.measures: list[MeasureConfig] = measure_configs(entry)
        self.rooms: list[RoomConfig] = room_configs(entry)
        self._last_room_records: list[Any] = []
        self._metered_room_prices: dict[str, dict[date, float]] = {}
        self.site: Any = None
        self.backfill_progress: dict[str, Any] | None = None
        self._last_metrics: list[DayMetrics] = []
        self._last_weather_update: datetime | None = None
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._climatology_task: asyncio.Task[Any] | None = None

    # --- lifecycle ---------------------------------------------------------------------

    async def _async_setup(self) -> None:
        """Load the store and build the core site model."""
        await self.store.async_load()
        try:
            self.site = build_site_from_entry(self.entry)
        except Exception as err:  # noqa: BLE001 - surfaces config/core mismatches as setup errors
            raise UpdateFailed(f"Could not build site model: {err}") from err
        signature = weather_signature(self.entry)
        if self.store.get_meta(META_WEATHER_SIGNATURE) != signature:
            _LOGGER.info("Weather source of %s changed, history will be rebuilt", self.site_name)
            self.store.clear_weather_cache()
            self.store.set_meta(META_WEATHER_SIGNATURE, signature)
            self.store.set_meta(META_BACKFILL_DONE, False)
            self.store.set_meta_date(META_LAST_DEFINITIVE_DATE, None)

    @callback
    def async_start(self) -> None:
        """Schedule the daily run and start pending background work."""
        self.entry.async_on_unload(
            async_track_time_change(
                self.hass,
                self._async_daily_trigger,
                hour=DAILY_RUN_TIME.hour,
                minute=DAILY_RUN_TIME.minute,
                second=0,
            )
        )
        history = history_options(self.entry)
        if not self.store.get_meta(META_BACKFILL_DONE):
            years = int(history.get(CONF_BACKFILL_YEARS, 0))
            self._start_background(self.async_backfill(years), "backfill")
        else:
            recompute_from = history.get(CONF_RECOMPUTE_FROM)
            # The options flow stores a fresh token with every recompute request so the
            # same date can be requested again.
            marker = f"{recompute_from}|{history.get('recompute_token', '')}"
            if recompute_from and self.store.get_meta(META_RECOMPUTE_MARKER) != marker:
                self.store.set_meta(META_RECOMPUTE_MARKER, marker)
                self._start_background(
                    self.async_recompute(date.fromisoformat(str(recompute_from))), "recompute"
                )
        if history.get(CONF_IMPORT_NOW) and not self.store.get_meta("import_hint_shown"):
            self.store.set_meta("import_hint_shown", True)
            persistent_notification.async_create(
                self.hass,
                "Meter readings from before your Home Assistant history can be imported from "
                "Settings → Devices & services → Heatprint → Configure → Import meter readings "
                "(paste a CSV or pick a file under /config). A mindergas.nl export "
                "(datum;stand) needs no extra questions. The action "
                "`heatprint.import_readings` remains available for automations.",
                title=f"Heatprint {self.site_name}: import meter readings",
                notification_id=NOTIFICATION_IMPORT_HINT.format(entry_id=self.entry.entry_id),
            )

    async def async_shutdown(self) -> None:
        """Cancel background work and flush the store."""
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        await self.store.async_save()
        await super().async_shutdown()

    def _start_background(self, coro: Any, name: str) -> asyncio.Task[Any]:
        """Run a coroutine as a background task bound to the config entry."""
        task = self.entry.async_create_background_task(
            self.hass, coro, f"{DOMAIN}_{name}_{self.entry.entry_id}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @callback
    def _async_schedule_climatology_refresh(self) -> None:
        """Rebuild the climatology in the background when its signature is stale.

        The signature changes once a year, with the climatology years, with the
        weather source and when the fitted balance temperature moves by a whole
        degree (the house degree-day series depends on it, METHODS 8.1/8.5). The
        initial backfill builds the climatology itself.
        """
        if not self.store.get_meta(META_BACKFILL_DONE):
            return
        if self._climatology_task is not None and not self._climatology_task.done():
            return
        if self.store.get_meta(META_CLIMATOLOGY_SIGNATURE) == self._climatology_signature():
            return
        self._climatology_task = self._start_background(
            self._async_refresh_climatology_task(), "climatology"
        )

    async def _async_refresh_climatology_task(self) -> None:
        """Background wrapper around _async_refresh_climatology."""
        try:
            await self._async_refresh_climatology()
            await self.store.async_save()
        except asyncio.CancelledError:
            raise
        except (CoreError, HomeAssistantError) as err:
            _LOGGER.warning("Climatology refresh for %s failed: %s", self.site_name, err)
            return
        except Exception:  # noqa: BLE001 - background task, keep the integration alive
            _LOGGER.exception("Climatology refresh for %s failed unexpectedly", self.site_name)
            return
        await self.async_request_refresh()

    async def _async_daily_trigger(self, now: datetime) -> None:
        """Time trigger at DAILY_RUN_TIME."""
        await self.async_refresh()

    # --- daily run ------------------------------------------------------------------------

    @property
    def today(self) -> date:
        """Return today's local date for the site."""
        return dt_util.now(self.tz).date()

    async def _async_update_data(self) -> HeatprintData:
        """Run the daily pipeline for the recent window and build the snapshot."""
        if self.site is None:
            raise UpdateFailed("Site model not available")
        try:
            async with self._lock:
                await self._async_daily_run()
                snapshot = await self._async_build_snapshot()
        except CoreError as err:
            raise UpdateFailed(f"Weather or core error: {err}") from err
        except HomeAssistantError as err:
            raise UpdateFailed(str(err)) from err
        self._async_schedule_climatology_refresh()
        return snapshot

    async def _async_daily_run(self) -> None:
        """Process last definitive day - 2 .. yesterday."""
        yesterday = self.today - timedelta(days=1)
        last_definitive = self.store.get_meta_date(META_LAST_DEFINITIVE_DATE)
        if last_definitive is None:
            start = yesterday - timedelta(days=INITIAL_WINDOW_DAYS)
        else:
            start = min(last_definitive - timedelta(days=2), yesterday)
        # A long outage is processed in chunks so the running sums stay consistent.
        await self._async_process_chunks(start, yesterday, locked=True)
        self.store.set_meta(META_LAST_RUN, dt_util.utcnow().isoformat())
        self.store.async_delay_save()
        await self._async_daily_mindergas_push()

    async def _async_build_records(
        self, start: date, end: date
    ) -> tuple[list[Any], list[WeatherDay]]:
        """Run the core pipeline for start..end without writing anything."""
        weather = await self._async_weather(start - timedelta(days=1), end)
        energy = await self._async_energy(start, end)
        baselines = await self._async_baselines()
        prices, hourly_electric, hourly_price, co2_live = await self._async_pricing_inputs(
            start, end
        )
        records = await self.hass.async_add_executor_job(
            lambda: build_daily_records(
                self.site,
                weather,
                energy,
                baselines,
                self.store.latest_fit,
                start,
                end,
                effective_co2_factors(self.entry, self.generators, co2_live),
                prices,
                hourly_electric,
                hourly_price,
            )
        )
        return records, weather

    async def _async_pricing_inputs(
        self, start: date, end: date
    ) -> tuple[
        dict[str, dict[date, float]],
        dict[str, dict[date, dict[int, float]]],
        dict[str, dict[date, dict[int, float]]],
        dict[date, float],
    ]:
        """Read daily (and hourly dynamic) price/CO₂ series from the recorder."""
        price_entities = {
            generator.price_entity for generator in self.generators if generator.price_entity
        }
        room_price_entities = {
            room.price_entity
            for room in self.rooms
            if room.enabled and room.is_metered and room.price_entity
        }
        co2_entity = pricing_options(self.entry).get(CONF_CO2_ENTITY) or self.entry.options.get(
            OPT_PRICING, {}
        ).get(CONF_CO2_ENTITY)
        mean_entities = set(price_entities) | set(room_price_entities)
        if co2_entity:
            mean_entities.add(co2_entity)
        means = await async_daily_means(self.hass, mean_entities, start, end, self.tz)
        prices: dict[str, dict[date, float]] = {}
        for generator in self.generators:
            if not generator.price_entity:
                continue
            series = means.get(generator.price_entity, {})
            if series:
                prices[generator.generator_id] = dict(series)
        hourly_electric: dict[str, dict[date, dict[int, float]]] = {}
        hourly_price: dict[str, dict[date, dict[int, float]]] = {}
        dynamic = [
            generator
            for generator in self.generators
            if generator.price_mode == PRICE_MODE_DYNAMIC and generator.is_electric
        ]
        if dynamic:
            electric_ids = {
                generator.electric_entity or generator.energy_entity
                for generator in dynamic
                if generator.electric_entity or generator.energy_entity
            }
            price_ids = {generator.price_entity for generator in dynamic if generator.price_entity}
            hourly_e = await async_hourly_changes(self.hass, electric_ids, start, end, self.tz)
            hourly_p = await async_hourly_means(self.hass, price_ids, start, end, self.tz)
            for generator in dynamic:
                electric_id = generator.electric_entity or generator.energy_entity
                if electric_id and hourly_e.get(electric_id):
                    hourly_electric[generator.generator_id] = hourly_e[electric_id]
                if generator.price_entity and hourly_p.get(generator.price_entity):
                    hourly_price[generator.generator_id] = hourly_p[generator.price_entity]
        self._metered_room_prices = {
            room.room_id: dict(means.get(room.price_entity, {}))
            for room in self.rooms
            if room.enabled and room.is_metered and room.price_entity
        }
        co2_live = dict(means.get(co2_entity, {})) if co2_entity else {}
        return prices, hourly_electric, hourly_price, co2_live

    def _rooms_allocation_enabled(self) -> bool:
        """True when rooms options enable allocation and at least one room is enabled."""
        if not rooms_options(self.entry).get(CONF_ROOMS_ALLOCATION, True):
            return False
        return any(room.enabled for room in self.rooms)

    async def _async_room_demands(
        self, start: date, end: date
    ) -> dict[date, dict[str, dict[str, Any]]]:
        """Read daily demand and room temperature, preferring statistics."""
        demand_entities = {
            room.demand_entity for room in self.rooms if room.enabled and room.demand_entity
        }
        temp_entities = {
            room.temperature_entity
            for room in self.rooms
            if room.enabled and room.temperature_entity
        }
        metered = {
            room.demand_entity
            for room in self.rooms
            if room.enabled and room.is_metered and room.demand_entity
        }
        climate_demand = {
            room.demand_entity
            for room in self.rooms
            if room.enabled and demand_requires_history(room.demand_entity, room.demand_kind)
        }
        means_entities = (demand_entities - metered - climate_demand) | temp_entities
        means = await async_daily_means(self.hass, means_entities, start, end, self.tz)
        sums = await async_daily_sums(self.hass, metered, start, end, self.tz)
        missing_demand = [
            entity
            for entity in demand_entities
            if entity in climate_demand or (not means.get(entity) and not sums.get(entity))
        ]
        missing_temp = [entity for entity in temp_entities if not means.get(entity)]
        heating_history = (
            await async_daily_from_history(
                self.hass, climate_demand, start, end, self.tz, mode="heating"
            )
            if climate_demand
            else {}
        )
        numeric_missing = [entity for entity in missing_demand if entity not in climate_demand]
        numeric_history = (
            await async_daily_from_history(
                self.hass, numeric_missing, start, end, self.tz, mode="auto"
            )
            if numeric_missing
            else {}
        )
        temp_history = (
            await async_daily_from_history(
                self.hass, missing_temp, start, end, self.tz, mode="temperature"
            )
            if missing_temp
            else {}
        )
        result: dict[date, dict[str, dict[str, Any]]] = {}
        for room in self.rooms:
            if not room.enabled:
                continue
            for day in _daterange(start, end):
                raw: float | None = None
                from_history = False
                if room.demand_entity:
                    if room.is_metered:
                        raw = sums.get(room.demand_entity, {}).get(day)
                    elif room.demand_entity not in climate_demand:
                        raw = means.get(room.demand_entity, {}).get(day)
                    if raw is None:
                        if room.demand_entity in climate_demand:
                            raw = heating_history.get(room.demand_entity, {}).get(day)
                        else:
                            raw = numeric_history.get(room.demand_entity, {}).get(day)
                        from_history = raw is not None
                t_room = None
                if room.temperature_entity:
                    t_room = means.get(room.temperature_entity, {}).get(day)
                    if t_room is None:
                        t_room = temp_history.get(room.temperature_entity, {}).get(day)
                result.setdefault(day, {})[room.room_id] = {
                    "raw": raw,
                    "t_room_mean": t_room,
                    "from_history": from_history,
                }
        return result

    async def _async_allocate_rooms(
        self, records: list[Any], start: date, end: date
    ) -> tuple[list[Any], dict[date, float]]:
        """Allocate site space heat across configured rooms."""
        inputs = await self._async_room_demands(start, end)
        metered_by_day: dict[date, dict[str, float]] = {}
        for room_id, days in self._metered_room_prices.items():
            for day, price in days.items():
                metered_by_day.setdefault(day, {})[room_id] = price
        return await self.hass.async_add_executor_job(
            allocate_rooms,
            self.site,
            records,
            inputs,
            output_w_per_m2_table(self.entry),
            metered_by_day,
        )

    async def _async_process_window(
        self, start: date, end: date, sum_offsets: Mapping[str, float] | None = None
    ) -> tuple[list[DayMetrics], dict[str, float]]:
        """Run the pipeline for start..end and write the results."""
        records, weather = await self._async_build_records(start, end)
        provisional_days = {day.date for day in weather if day.provisional}
        metrics = [record_to_metrics(record, self.generators) for record in records]
        for day in metrics:
            if day.date in provisional_days:
                day.provisional = True
        if self._rooms_allocation_enabled():
            room_records, unallocated = await self._async_allocate_rooms(records, start, end)
            min_days = int(rooms_options(self.entry)[CONF_ROOMS_MIN_FIT_DAYS])
            apply_room_not_fitted(
                room_records,
                records,
                min_days=min_days,
                skip_room_ids=self.store.all_latest_room_fits(),
            )
            merge_room_metrics(metrics, room_records, unallocated, self.rooms)
            self._last_room_records = room_records
            for record in room_records:
                self.store.set_room_flags(record.room_id, record.date, record_flags(record))
        carried = await async_write_daily_metrics(
            self.hass,
            self.site_id,
            self.site_name,
            metrics,
            self.generators,
            self.tz,
            sum_offsets,
            rooms=self.rooms,
        )
        for day in metrics:
            self.store.set_flags(day.date, day.flags)
        definitive = max((day.date for day in metrics if not day.provisional), default=None)
        if definitive is not None:
            existing = self.store.get_meta_date(META_LAST_DEFINITIVE_DATE)
            if existing is None or definitive > existing:
                self.store.set_meta_date(META_LAST_DEFINITIVE_DATE, definitive)
        if metrics:
            self._last_metrics = metrics
        return metrics, carried

    async def _async_process_chunks(
        self, start: date, end: date, *, locked: bool, label: str | None = None
    ) -> int:
        """Process start..end in chunks of BACKFILL_CHUNK_DAYS, carrying the running sums.

        ``locked`` tells whether the caller already holds the processing lock.
        Returns the number of processed days.
        """
        total_days = (end - start).days + 1
        processed = 0
        carried: dict[str, float] | None = None
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=BACKFILL_CHUNK_DAYS - 1), end)
            if locked:
                _metrics, carried = await self._async_process_window(
                    chunk_start, chunk_end, carried
                )
            else:
                async with self._lock:
                    _metrics, carried = await self._async_process_window(
                        chunk_start, chunk_end, carried
                    )
            processed += (chunk_end - chunk_start).days + 1
            if label is not None:
                self.backfill_progress = {
                    "label": label,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "processed_days": processed,
                    "total_days": total_days,
                }
                _LOGGER.info(
                    "%s %s: %d/%d days processed (%s - %s)",
                    label,
                    self.site_name,
                    processed,
                    total_days,
                    chunk_start,
                    chunk_end,
                )
            self.store.async_delay_save()
            chunk_start = chunk_end + timedelta(days=1)
        return processed

    async def _async_weather(self, start: date, end: date) -> list[WeatherDay]:
        """Return weather days for start..end from cache, provider or HA sensors."""
        weather_cfg = self.entry.data.get(CONF_WEATHER, {})
        if weather_cfg.get(CONF_PROVIDER) == PROVIDER_HA_SENSORS:
            entities = weather_cfg.get(CONF_HA_ENTITIES, {})
            means = await async_daily_means(self.hass, entities.values(), start, end, self.tz)
            days = weather_from_ha_sensors(weather_cfg, means, start, end)
        else:
            cached = self.store.cached_weather(start, end)
            missing = [
                day
                for day in _daterange(start, end)
                if day not in cached or cached[day].provisional
            ]
            if missing:
                fetched = await async_fetch_weather(
                    async_get_clientsession(self.hass),
                    weather_cfg,
                    float(self.entry.data[CONF_LATITUDE]),
                    float(self.entry.data[CONF_LONGITUDE]),
                    min(missing),
                    max(missing),
                    timezone=self.entry.data[CONF_TIMEZONE],
                )
                for day in fetched:
                    # Never replace a definitive day by a provisional one.
                    current = cached.get(day.date)
                    if current is not None and not current.provisional and day.provisional:
                        continue
                    cached[day.date] = day
            days = [cached[day] for day in sorted(cached)]
        self.store.update_weather_cache(days)
        self._last_weather_update = dt_util.utcnow()
        if days:
            async_clear_weather_check_failed(self.hass, self.site_id)
        return days

    async def _async_energy(
        self, start: date, end: date
    ) -> dict[str, dict[date, DailyEnergyInput]]:
        """Read daily consumption per generator from the recorder, merged with imports."""
        entities: set[str] = set()
        for generator in self.generators:
            entities |= generator.entities
        sums = await async_daily_sums(self.hass, entities, start, end, self.tz)
        result: dict[str, dict[date, DailyEnergyInput]] = {}
        for generator in self.generators:
            imported = self.store.imported(generator.generator_id, start, end)
            days: dict[date, DailyEnergyInput] = {}

            def _value(entity: str | None, day: date) -> float | None:
                return sums.get(entity, {}).get(day) if entity else None

            for day in _daterange(start, end):
                carrier = _value(generator.energy_entity, day)
                is_imported = False
                if carrier is None and day in imported:
                    carrier = imported[day]
                    is_imported = True
                item = DailyEnergyInput(
                    carrier=carrier,
                    thermal=_value(generator.thermal_entity, day),
                    electric=_value(generator.electric_entity, day),
                    dhw=_value(generator.dhw_entity, day),
                    dhw_electric=_value(generator.dhw_electric_entity, day),
                    imported=is_imported,
                )
                if item.carrier is None and item.thermal is None and item.electric is None:
                    continue
                days[day] = item
            result[generator.generator_id] = days
        return result

    async def _async_baselines(self) -> dict[str, float]:
        """Return DHW baselines per generator, refreshing them when missing or stale."""
        baselines = self.store.baselines
        needed = [
            generator
            for generator in self.generators
            if generator.role == ROLE_BOTH and generator.dhw_mode in (DHW_BASELINE, DHW_MEASURED)
        ]
        if not needed:
            return baselines
        computed_at = self.store.get_meta_date(META_BASELINES_AT)
        fresh = computed_at is not None and (self.today - computed_at).days < BASELINE_REFRESH_DAYS
        if fresh and all(generator.generator_id in baselines for generator in needed):
            return baselines
        # Mark the attempt first so a failure does not retry on every run.
        self.store.set_meta_date(META_BASELINES_AT, self.today)
        end = self.today - timedelta(days=1)
        energy = await self._async_energy(end - timedelta(days=WEATHER_CACHE_DAYS), end)
        try:
            computed = await self.hass.async_add_executor_job(estimate_baselines, self.site, energy)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("DHW baseline could not be computed: %s", err)
            return baselines
        if computed:
            baselines.update(computed)
            self.store.set_baselines(baselines)
        return baselines

    # --- snapshot -------------------------------------------------------------------------

    async def _async_build_snapshot(self) -> HeatprintData:
        """Build the HeatprintData snapshot from statistics, the store and season records."""
        yesterday = self.today - timedelta(days=1)
        season = season_for(self.entry, yesterday)
        aggregate = await self._async_season_aggregate(season, yesterday)
        records, _weather = await self._async_build_records(season.start, yesterday)
        self._apply_record_costs(aggregate, records)
        fit = await self._async_maybe_fit(season, records)
        room_fits = await self._async_maybe_fit_rooms(season, records)
        forecast = await self._async_forecast(season, aggregate, records, fit)
        quality = await self._async_data_quality(yesterday)
        primary = method_options(self.entry)[CONF_METHODS_PRIMARY]
        if primary == METHOD_HOUSE and fit is None:
            primary = FALLBACK_METHOD_PRIMARY
        return HeatprintData(
            latest=self._latest_day(),
            season=aggregate,
            fit=fit,
            forecast=forecast,
            dhw_baseline=baselines_in_kwh(self.site, self.store.baselines),
            data_quality=quality,
            last_weather_update=self._last_weather_update,
            primary_method=primary,
            last_run=dt_util.utcnow(),
            room_fits=room_fits,
        )

    def _latest_day(self) -> LatestDay | None:
        """Return the newest processed day with any value."""
        if not self._last_metrics:
            return None
        newest = max(self._last_metrics, key=lambda item: item.date)
        return LatestDay(
            date=newest.date,
            t_mean=newest.values.get(METRIC_T_MEAN),
            tac_primary=newest.tac_primary,
            dd={
                method: value
                for method, metric in METHOD_TO_DD_METRIC.items()
                if (value := newest.values.get(metric)) is not None
            },
            heat_space_kwh=newest.values.get(METRIC_HEAT_SPACE),
            heat_dhw_kwh=newest.values.get(METRIC_HEAT_DHW),
            cost_eur=newest.values.get(METRIC_COST),
            co2_kg=newest.values.get(METRIC_CO2),
            cop=newest.cop,
            flags=list(newest.flags),
            provisional=newest.provisional,
        )

    def _sum_ids(self) -> list[str]:
        """Return the statistic ids of all sum metrics of the site."""
        ids = [
            statistic_id(self.site_id, metric)
            for metric in (
                *METHOD_TO_DD_METRIC.values(),
                METRIC_HEAT_SPACE,
                METRIC_HEAT_DHW,
                METRIC_HEAT_UNALLOCATED,
                METRIC_GAS,
                METRIC_ELECTRIC_HP,
                METRIC_COST,
                METRIC_CO2,
            )
        ]
        for room in self.rooms:
            ids.append(statistic_id(self.site_id, room_heat_metric(room.room_id)))
            ids.append(statistic_id(self.site_id, room_cost_metric(room.room_id)))
        for generator in self.generators:
            ids.append(statistic_id(self.site_id, generator_metric(generator.generator_id)))
            if generator.role in (ROLE_BOTH, ROLE_DHW):
                ids.append(statistic_id(self.site_id, generator_dhw_metric(generator.generator_id)))
        return ids

    async def _async_season_aggregate(self, season: SeasonWindow, end: date) -> SeasonAggregate:
        """Sum the site's own statistics from the season start to ``end``."""
        data = await async_daily_metrics(self.hass, self._sum_ids(), [], season.start, end, self.tz)

        def _total(metric: str) -> float:
            return float(sum(data.get(statistic_id(self.site_id, metric), {}).values()))

        aggregate = SeasonAggregate(label=season.label, start=season.start, end=season.end)
        aggregate.days = len(data.get(statistic_id(self.site_id, METRIC_HEAT_SPACE), {}))
        aggregate.dd = {method: _total(metric) for method, metric in METHOD_TO_DD_METRIC.items()}
        aggregate.heat_space_kwh = _total(METRIC_HEAT_SPACE)
        aggregate.heat_dhw_kwh = _total(METRIC_HEAT_DHW)
        aggregate.gas_m3 = _total(METRIC_GAS)
        aggregate.electric_hp_kwh = _total(METRIC_ELECTRIC_HP)
        heat_pump_space = 0.0
        for generator in self.generators:
            item = GeneratorAggregate(
                generator.generator_id,
                generator.name,
                generator.kind,
                price_mode=generator.price_mode,
            )
            item.heat_space_kwh = _total(generator_metric(generator.generator_id))
            if generator.role in (ROLE_BOTH, ROLE_DHW):
                item.heat_dhw_kwh = _total(generator_dhw_metric(generator.generator_id))
            if aggregate.heat_space_kwh > 0:
                item.share = item.heat_space_kwh / aggregate.heat_space_kwh
            if generator.is_heat_pump:
                heat_pump_space += item.heat_space_kwh
            aggregate.per_generator[generator.generator_id] = item
        if aggregate.heat_space_kwh > 0 and any(g.is_heat_pump for g in self.generators):
            aggregate.share_heat_pump = heat_pump_space / aggregate.heat_space_kwh
        aggregate.heat_per_dd = {
            method: aggregate.heat_space_kwh / dd
            for method, dd in aggregate.dd.items()
            if dd > 0 and aggregate.heat_space_kwh > 0
        }
        dd_classic = aggregate.dd.get("classic", 0.0)
        if dd_classic > 0 and aggregate.gas_m3 > 0:
            aggregate.gas_per_dd_classic = aggregate.gas_m3 / dd_classic
        aggregate.heat_unallocated_kwh = _total(METRIC_HEAT_UNALLOCATED)
        aggregate.cost_eur = _total(METRIC_COST)
        aggregate.co2_kg = _total(METRIC_CO2)
        latest_by_room = {
            record.room_id: record for record in self._last_room_records if self._last_room_records
        }
        yesterday = self.today - timedelta(days=1)
        for room in self.rooms:
            if not room.enabled:
                continue
            item = RoomAggregate(room.room_id, room.name, floor_area_m2=room.floor_area_m2)
            item.heat_kwh = _total(room_heat_metric(room.room_id))
            item.cost_eur = _total(room_cost_metric(room.room_id))
            if aggregate.heat_space_kwh > 0:
                item.share = item.heat_kwh / aggregate.heat_space_kwh
            if room.floor_area_m2 and room.floor_area_m2 > 0:
                item.heat_per_m2 = item.heat_kwh / room.floor_area_m2
                if item.cost_eur:
                    item.cost_per_m2 = item.cost_eur / room.floor_area_m2
            latest = latest_by_room.get(room.room_id)
            if latest is not None and latest.date == yesterday:
                item.heat_yesterday_kwh = latest.heat_room_kwh
                item.cost_yesterday_eur = latest.cost_room_eur
                item.flags = record_flags(latest)
            fit = self.store.latest_room_fit(room.room_id)
            if fit:
                item.fit = fit
                item.ua_w_per_k = fit.get("ua_w_per_k")
                item.ua_w_per_k_per_m2 = fit.get("ua_w_per_k_per_m2")
                item.ua_indicative_w_per_k = fit.get("ua_indicative_w_per_k")
                item.balance_temp = fit.get("balance_temp")
            window_start = end - timedelta(days=DATA_QUALITY_WINDOW_DAYS - 1)
            room_flags = self.store.room_flags_between(room.room_id, window_start, end)
            usable_days = sum(
                1
                for day in _daterange(window_start, end)
                if "ROOM_DEMAND_MISSING" not in room_flags.get(day, [])
            )
            item.data_quality = usable_days / DATA_QUALITY_WINDOW_DAYS
            aggregate.per_room[room.room_id] = item
        has_cost = any((room.cost_eur or 0.0) > 0 for room in aggregate.per_room.values())
        aggregate.room_ranked_by = "cost_eur" if has_cost else "heat_kwh"
        heat_ranking = sorted(
            aggregate.per_room.values(),
            key=lambda room: room.heat_kwh,
            reverse=True,
        )
        cost_ranking = sorted(
            aggregate.per_room.values(),
            key=lambda room: float(room.cost_eur or 0.0),
            reverse=True,
        )
        ranking = cost_ranking if has_cost else heat_ranking
        aggregate.room_ranking = [
            {
                "room_id": room.room_id,
                "name": room.name,
                "heat_kwh": room.heat_kwh,
                "cost_eur": room.cost_eur,
                "share": room.share,
            }
            for room in ranking
            if room.heat_kwh > 0 or (room.cost_eur or 0.0) > 0
        ]
        aggregate.room_ranking_by_heat = [
            {
                "room_id": room.room_id,
                "name": room.name,
                "heat_kwh": room.heat_kwh,
                "share": room.share,
            }
            for room in heat_ranking
            if room.heat_kwh > 0
        ]
        if aggregate.room_ranking:
            aggregate.most_expensive_room = aggregate.room_ranking[0]["name"]
        by_loss = sorted(
            (room for room in aggregate.per_room.values() if room.ua_w_per_k),
            key=lambda room: float(room.ua_w_per_k or 0),
            reverse=True,
        )
        aggregate.room_ranking_by_heat_loss = [
            {
                "room_id": room.room_id,
                "name": room.name,
                "ua_w_per_k": room.ua_w_per_k,
                "ua_w_per_k_per_m2": room.ua_w_per_k_per_m2,
            }
            for room in by_loss
        ]
        return aggregate

    def _apply_record_costs(self, aggregate: SeasonAggregate, records: list[Any]) -> None:
        """Fill space-heating cost and per-generator weighted prices from season records."""
        space = 0.0
        has_space = False
        generator_cost: dict[str, float] = {item.generator_id: 0.0 for item in self.generators}
        generator_electric: dict[str, float] = {item.generator_id: 0.0 for item in self.generators}
        for record in records:
            if record.cost_space_eur is not None:
                space += float(record.cost_space_eur)
                has_space = True
            by_generator = record.heat_by_generator or {}
            for generator in self.generators:
                energy = by_generator.get(generator.generator_id)
                if energy is None:
                    continue
                if energy.cost_eur is not None:
                    generator_cost[generator.generator_id] += float(energy.cost_eur)
                if energy.electric_kwh is not None:
                    generator_electric[generator.generator_id] += float(energy.electric_kwh)
        if has_space:
            aggregate.cost_space_eur = space
        elif aggregate.cost_eur > 0 and aggregate.heat_space_kwh + aggregate.heat_dhw_kwh > 0:
            total_heat = aggregate.heat_space_kwh + aggregate.heat_dhw_kwh
            aggregate.cost_space_eur = aggregate.cost_eur * (aggregate.heat_space_kwh / total_heat)
        for generator in self.generators:
            item = aggregate.per_generator.get(generator.generator_id)
            if item is None:
                continue
            item.price_mode = generator.price_mode
            item.cost_eur = generator_cost.get(generator.generator_id) or None
            item.electric_kwh = generator_electric.get(generator.generator_id, 0.0)
            if item.electric_kwh > 0 and item.cost_eur is not None:
                item.avg_price_paid = item.cost_eur / item.electric_kwh

    async def _async_maybe_fit(
        self, season: SeasonWindow, records: list[Any]
    ) -> dict[str, Any] | None:
        """Refresh the house fit when enough usable days exist and the last fit is old."""
        latest = self.store.latest_fit
        yesterday = self.today - timedelta(days=1)
        min_days = int(advanced_options(self.entry)[CONF_MIN_FIT_DAYS])
        usable = sum(1 for record in records if record_is_usable(record))
        last_fit_at = self.store.get_meta(META_LAST_FIT_AT)
        last_fit = dt_util.parse_datetime(last_fit_at) if last_fit_at else None
        due = last_fit is None or (dt_util.utcnow() - last_fit) > timedelta(days=FIT_REFRESH_DAYS)
        if usable < min_days or not due:
            return latest
        try:
            fit = await self._async_fit(records, season.start, yesterday)
        except (CoreError, HomeAssistantError) as err:
            _LOGGER.warning("Signature fit failed for %s: %s", self.site_name, err)
            return latest
        return fit or latest

    async def _async_maybe_fit_rooms(
        self, season: SeasonWindow, records: list[Any]
    ) -> dict[str, dict[str, Any]]:
        """Refresh per-room fits when allocation is on and enough days exist."""
        latest = self.store.all_latest_room_fits()
        if not self._rooms_allocation_enabled() or not self._last_room_records:
            return latest
        yesterday = self.today - timedelta(days=1)
        min_days = int(rooms_options(self.entry)[CONF_ROOMS_MIN_FIT_DAYS])
        last_fit_at = self.store.get_meta(META_LAST_ROOM_FIT_AT)
        last_fit = dt_util.parse_datetime(last_fit_at) if last_fit_at else None
        due = last_fit is None or (dt_util.utcnow() - last_fit) > timedelta(days=FIT_REFRESH_DAYS)
        if not due:
            return latest
        core_rooms = {room.id: room for room in getattr(self.site, "rooms", [])}
        by_room: dict[str, list[Any]] = {}
        for record in self._last_room_records:
            by_room.setdefault(record.room_id, []).append(record)
        advanced = advanced_options(self.entry)
        for room_id, room_records in by_room.items():
            core_room = core_rooms.get(room_id)
            if core_room is None:
                continue
            try:
                fit = await self.hass.async_add_executor_job(
                    lambda cr=core_room, rr=room_records: fit_room_signature(
                        cr,
                        rr,
                        records,
                        start=season.start,
                        end=yesterday,
                        min_days=min_days,
                        outlier_k=float(advanced[CONF_OUTLIER_THRESHOLD]),
                    )
                )
            except (CoreError, HomeAssistantError) as err:
                _LOGGER.warning("Room fit failed for %s: %s", room_id, err)
                continue
            if fit is not None:
                self.store.add_room_fit(room_id, fit)
                latest[room_id] = fit
        self.store.set_meta(META_LAST_ROOM_FIT_AT, dt_util.utcnow().isoformat())
        self.store.async_delay_save()
        return latest

    async def _async_fit(
        self,
        records: list[Any],
        start: date,
        end: date,
        tac_preset: str = "house",
        fit_wind: bool | None = None,
    ) -> dict[str, Any] | None:
        """Run the fit in the executor and store the result."""
        advanced = advanced_options(self.entry)
        if fit_wind is None:
            fit_wind = bool(method_options(self.entry)[CONF_HOUSE_FIT_WIND])
        fit = await self.hass.async_add_executor_job(
            lambda: fit_signature(
                self.site,
                records,
                start=start,
                end=end,
                tac_preset=tac_preset,
                fit_wind=fit_wind,
                min_days=int(advanced[CONF_MIN_FIT_DAYS]),
                outlier_k=float(advanced[CONF_OUTLIER_THRESHOLD]),
            )
        )
        self.store.set_meta(META_LAST_FIT_AT, dt_util.utcnow().isoformat())
        if fit is not None:
            self.store.add_fit(fit)
        self.store.async_delay_save()
        return fit

    async def _async_forecast(
        self,
        season: SeasonWindow,
        aggregate: SeasonAggregate,
        records: list[Any],
        fit: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Compute the season forecast (METHODS 8.5)."""
        if aggregate.days == 0 or self.store.climatology is None:
            return self.store.forecast
        primary = method_options(self.entry)[CONF_METHODS_PRIMARY]
        if primary == METHOD_HOUSE and fit is None:
            primary = FALLBACK_METHOD_PRIMARY
        dhw_per_day = aggregate.heat_dhw_kwh / aggregate.days if aggregate.days else 0.0
        try:
            forecast = await self.hass.async_add_executor_job(
                lambda: forecast_season(
                    self.site,
                    records,
                    season=season,
                    climatology=self.store.climatology,
                    method=primary,
                    dhw_per_day=dhw_per_day,
                    fit=fit,
                    today=self.today,
                    generators=self.generators,
                )
            )
        except Exception as err:  # noqa: BLE001 - a failing forecast must not break the run
            _LOGGER.debug("Forecast not available for %s: %s", self.site_name, err)
            return self.store.forecast
        self.store.set_forecast(forecast)
        return forecast

    async def _async_data_quality(self, end: date) -> DataQuality:
        """Share of usable days in the last 30 days and the length of the current gap."""
        start = end - timedelta(days=DATA_QUALITY_WINDOW_DAYS - 1)
        data = await async_daily_metrics(
            self.hass, [statistic_id(self.site_id, METRIC_HEAT_SPACE)], [], start, end, self.tz
        )
        with_data = set(data.get(statistic_id(self.site_id, METRIC_HEAT_SPACE), {}))
        flags = self.store.flags_between(start, end)
        usable = {day for day in with_data if not EXCLUSION_FLAGS.intersection(flags.get(day, []))}
        gap = 0
        day = end
        while day >= start and day not in usable:
            gap += 1
            day -= timedelta(days=1)
        last_usable = max(usable) if usable else None
        return DataQuality(
            usable_share=len(usable) / DATA_QUALITY_WINDOW_DAYS,
            flag_counts=self.store.flag_counts(start, end),
            gap_days=gap,
            last_usable=last_usable,
        )

    # --- backfill / recompute ----------------------------------------------------------

    async def _async_run_range(self, start: date, end: date, label: str) -> int:
        """Run the pipeline over start..end in chunks with notifications; returns days."""
        notification_id = NOTIFICATION_BACKFILL.format(entry_id=self.entry.entry_id)
        total_days = (end - start).days + 1
        persistent_notification.async_create(
            self.hass,
            f"Heatprint is processing {total_days} days ({start} to {end}) for {self.site_name}. "
            "Sensors update when it is done.",
            title=f"Heatprint {label}",
            notification_id=notification_id,
        )
        try:
            processed = await self._async_process_chunks(start, end, locked=False, label=label)
        finally:
            self.backfill_progress = None
            persistent_notification.async_dismiss(self.hass, notification_id)
        persistent_notification.async_create(
            self.hass,
            f"Heatprint finished the {label} of {processed} days for {self.site_name}.",
            title=f"Heatprint {label}",
            notification_id=f"{notification_id}_done",
        )
        return processed

    async def async_backfill(self, years: int) -> None:
        """Backfill weather, statistics and climatology for ``years`` years (background)."""
        yesterday = self.today - timedelta(days=1)
        try:
            if years > 0:
                start = yesterday - timedelta(days=365 * years)
                await self._async_run_range(start, yesterday, "backfill")
            await self._async_refresh_climatology()
            self.store.set_meta(META_BACKFILL_DONE, True)
            await self.store.async_save()
        except asyncio.CancelledError:
            raise
        except (CoreError, HomeAssistantError) as err:
            _LOGGER.error("Backfill for %s failed: %s", self.site_name, err)
            return
        except Exception:  # noqa: BLE001 - background task, keep the integration alive
            _LOGGER.exception("Backfill for %s failed unexpectedly", self.site_name)
            return
        await self.async_request_refresh()

    async def async_recompute(self, from_date: date) -> int:
        """Recompute all day records from ``from_date`` to yesterday (background or service)."""
        yesterday = self.today - timedelta(days=1)
        if from_date > yesterday:
            return 0
        days = await self._async_run_range(from_date, yesterday, "recompute")
        await self.store.async_save()
        await self.async_request_refresh()
        return days

    def _house_balance_temp(self) -> float | None:
        """Return the balance temperature of the latest fit, if any."""
        balance = (self.store.latest_fit or {}).get("balance_temp")
        return float(balance) if balance is not None else None

    def _climatology_signature(self) -> str:
        """Signature of the stored climatology: weather source, years, year, balance temp.

        The balance temperature is rounded to whole degrees so weekly refits do not
        trigger a rebuild (the forecast copes with small differences, see
        core_api.forecast_season).
        """
        years = int(history_options(self.entry)[CONF_CLIMATOLOGY_YEARS])
        balance = self._house_balance_temp()
        balance_text = "-" if balance is None else str(round(balance))
        return f"{weather_signature(self.entry)}|{years}|{self.today.year}|{balance_text}"

    async def _async_refresh_climatology(self) -> None:
        """Fetch the climatology years of weather and store the climatology (METHODS 8.1).

        Network providers are fetched year by year; Home Assistant weather
        sensors reuse the daily-run path so a site without KNMI/Open-Meteo
        still gets a forecast from recorder history.
        """
        years = int(history_options(self.entry)[CONF_CLIMATOLOGY_YEARS])
        # Refreshed once a year (the year is part of the signature), on a source change
        # and when the fitted balance temperature changes (house degree-day series).
        signature = self._climatology_signature()
        if self.store.get_meta(META_CLIMATOLOGY_SIGNATURE) == signature and self.store.climatology:
            return
        end = date(self.today.year, 1, 1) - timedelta(days=1)
        weather_cfg = self.entry.data.get(CONF_WEATHER, {})
        if weather_cfg.get(CONF_PROVIDER) == PROVIDER_HA_SENSORS:
            history = await self._async_weather(date(end.year - years + 1, 1, 1), end)
        else:
            session = async_get_clientsession(self.hass)
            history: list[WeatherDay] = []
            for year in range(end.year - years + 1, end.year + 1):
                history.extend(
                    await async_fetch_weather(
                        session,
                        weather_cfg,
                        float(self.entry.data[CONF_LATITUDE]),
                        float(self.entry.data[CONF_LONGITUDE]),
                        date(year, 1, 1),
                        date(year, 12, 31),
                        timezone=self.entry.data[CONF_TIMEZONE],
                    )
                )
        if not history:
            _LOGGER.debug("No weather history for climatology of %s", self.site_name)
            return
        climatology = await self.hass.async_add_executor_job(
            build_climatology, self.site, history, years, self._house_balance_temp()
        )
        self.store.set_climatology(climatology)
        self.store.set_meta(META_CLIMATOLOGY_SIGNATURE, signature)

    # --- service backends -----------------------------------------------------------------

    async def async_import_readings(
        self, generator_id: str, readings: list[tuple[datetime, float]]
    ) -> dict[str, Any]:
        """Store imported meter readings as daily consumption and recompute from the first day."""
        generator = self.generator(generator_id)
        consumption, flags = await self.hass.async_add_executor_job(
            daily_consumption_from_readings, readings, self.tz
        )
        # The store keeps plain daily amounts, so days that METHODS 9 excludes
        # (partial first/last day, meter reset) are not imported at all; interpolated
        # days are kept (allowed in fits with weight 1).
        consumption = {
            day: amount
            for day, amount in consumption.items()
            if not EXCLUSION_FLAGS.intersection(flags.get(day, []))
        }
        if not consumption:
            return {"imported_days": 0, "gaps": []}
        self.store.set_imported(generator.generator_id, consumption)
        first, last = min(consumption), max(consumption)
        gaps: list[dict[str, str]] = []
        gap_start: date | None = None
        for day in _daterange(first, last):
            if day in consumption:
                if gap_start is not None:
                    gaps.append(
                        {
                            "start": gap_start.isoformat(),
                            "end": (day - timedelta(days=1)).isoformat(),
                        }
                    )
                    gap_start = None
            elif gap_start is None:
                gap_start = day
        await self.store.async_save()
        self._start_background(self.async_recompute(first), "import_recompute")
        return {
            "imported_days": len(consumption),
            "first_day": first.isoformat(),
            "last_day": last.isoformat(),
            "flagged_days": len(flags),
            "gaps": gaps,
        }

    async def async_fit_signature(
        self,
        start: date,
        end: date,
        tac_preset: str = "house",
        fit_wind: bool | None = None,
    ) -> dict[str, Any]:
        """Fit the energy signature for a period, store it and return it."""
        records, _weather = await self._async_build_records(start, end)
        fit = await self._async_fit(records, start, end, tac_preset, fit_wind)
        if fit is None:
            raise HomeAssistantError(
                "Not enough usable days for a fit (at least 30 days with weather and energy)"
            )
        return fit

    async def async_fit_room_signature(
        self, room_id: str, start: date, end: date
    ) -> dict[str, Any]:
        """Fit one room's energy signature for a period and store it."""
        room = next((item for item in self.rooms if item.room_id == room_id), None)
        if room is None:
            raise HomeAssistantError(f"Unknown room {room_id}")
        records, _weather = await self._async_build_records(start, end)
        room_records, _unallocated = await self._async_allocate_rooms(records, start, end)
        only = [record for record in room_records if record.room_id == room_id]
        core_room = self.site.room(room_id)
        min_days = int(rooms_options(self.entry)[CONF_ROOMS_MIN_FIT_DAYS])
        advanced = advanced_options(self.entry)
        fit = await self.hass.async_add_executor_job(
            lambda: fit_room_signature(
                core_room,
                only,
                records,
                start=start,
                end=end,
                min_days=min_days,
                outlier_k=float(advanced[CONF_OUTLIER_THRESHOLD]),
            )
        )
        if fit is None:
            raise HomeAssistantError(
                "Not enough usable days for a room fit (at least 30 days with demand and heat)"
            )
        self.store.add_room_fit(room_id, fit)
        self.store.async_delay_save()
        return fit

    async def async_compare_periods(
        self, base: tuple[date, date], target: tuple[date, date], method: str
    ) -> dict[str, Any]:
        """Compare two periods with the given method."""
        start = min(base[0], target[0])
        end = min(max(base[1], target[1]), self.today - timedelta(days=1))
        records, _weather = await self._async_build_records(start, end)
        advanced = advanced_options(self.entry)
        try:
            return await self.hass.async_add_executor_job(
                lambda: compare_periods(
                    self.site,
                    records,
                    base=base,
                    target=target,
                    method=method,
                    climatology=self.store.climatology,
                    fit_wind=bool(method_options(self.entry)[CONF_HOUSE_FIT_WIND]),
                    min_days=int(advanced[CONF_MIN_FIT_DAYS]),
                )
            )
        except InsufficientData as err:
            raise HomeAssistantError(f"Not enough data to compare: {err}") from err

    async def async_measure_effect(self, measure_id: str) -> dict[str, Any]:
        """Compare the season before a measure with the period after it (METHODS 8.4)."""
        measure = next((item for item in self.measures if item.measure_id == measure_id), None)
        if measure is None:
            raise HomeAssistantError(f"Unknown measure {measure_id}")
        yesterday = self.today - timedelta(days=1)
        if (yesterday - measure.date).days < 30:
            raise HomeAssistantError("At least 30 days after the measure date are needed")
        season_of_measure = season_for(self.entry, measure.date)
        base_season = season_for(self.entry, season_of_measure.start - timedelta(days=1))
        records, _weather = await self._async_build_records(base_season.start, yesterday)
        primary = method_options(self.entry)[CONF_METHODS_PRIMARY]
        advanced = advanced_options(self.entry)
        try:
            result = await self.hass.async_add_executor_job(
                lambda: measure_effect(
                    self.site,
                    records,
                    measure_date=measure.date,
                    climatology=self.store.climatology,
                    method=FALLBACK_METHOD_PRIMARY if primary == METHOD_HOUSE else primary,
                    fit_wind=bool(method_options(self.entry)[CONF_HOUSE_FIT_WIND]),
                    min_days=int(advanced[CONF_MIN_FIT_DAYS]),
                )
            )
        except InsufficientData as err:
            raise HomeAssistantError(f"Not enough data for the measure effect: {err}") from err
        result["measure"] = {
            "id": measure.measure_id,
            "name": measure.name,
            "date": measure.date.isoformat(),
            "category": measure.category,
        }
        return result

    async def async_forecast(self) -> dict[str, Any]:
        """Return the latest forecast (computed during the last run)."""
        if self.data and self.data.forecast:
            return dict(self.data.forecast)
        return dict(self.store.forecast or {})

    async def async_export_rows(self, start: date, end: date) -> list[dict[str, Any]]:
        """Return day rows (all metrics and flags) for a CSV export."""
        mean_ids = [
            statistic_id(self.site_id, metric)
            for metric in (METRIC_T_MEAN, METRIC_TAC_PBL, METRIC_TAC_HOUSE)
        ]
        data = await async_daily_metrics(self.hass, self._sum_ids(), mean_ids, start, end, self.tz)
        flags = self.store.flags_between(start, end)
        prefix = f"{DOMAIN}:{self.site_id}_"
        columns = [sid[len(prefix) :] for sid in (*mean_ids, *self._sum_ids())]
        rows: list[dict[str, Any]] = []
        for day in _daterange(start, end):
            row: dict[str, Any] = {"date": day.isoformat()}
            has_value = False
            for column in columns:
                value = data.get(f"{prefix}{column}", {}).get(day)
                row[column] = value
                has_value = has_value or value is not None
            if not has_value:
                continue
            row["flags"] = "|".join(flags.get(day, []))
            rows.append(row)
        return rows

    def statistic_ids_for(self, generator_id: str | None = None) -> list[str]:
        """Return the external statistic ids of the site, or of one generator."""
        if generator_id:
            self.generator(generator_id)
            return generator_clear_statistic_ids(self.site_id, generator_id)
        return site_clear_statistic_ids(
            self.site_id,
            generator_ids=[generator.generator_id for generator in self.generators],
            dhw_generator_ids=[
                generator.generator_id
                for generator in self.generators
                if generator.role in (ROLE_BOTH, ROLE_DHW)
            ],
            room_ids=[room.room_id for room in self.rooms],
        )

    async def async_clear_statistics(self, generator_id: str | None = None) -> dict[str, Any]:
        """Delete Heatprint external statistics for a generator or the whole site."""
        ids = self.statistic_ids_for(generator_id)
        await async_clear_statistics(self.hass, ids)
        return {"cleared": ids, "generator_id": generator_id}

    def generator(self, generator_id: str) -> GeneratorConfig:
        """Return the generator config or raise."""
        for generator in self.generators:
            if generator.generator_id == generator_id:
                return generator
        raise HomeAssistantError(f"Unknown generator {generator_id}")

    async def async_meter_reading(self, generator_id: str, day: date) -> float:
        """Return the meter reading of the generator's energy entity at the start of ``day``."""
        generator = self.generator(generator_id)
        if not generator.energy_entity:
            raise HomeAssistantError(f"Generator {generator_id} has no energy entity")
        reading = await async_meter_reading_at(self.hass, generator.energy_entity, day, self.tz)
        if reading is None:
            raise HomeAssistantError(f"No meter reading available for {day}")
        return reading

    async def async_push_reading(self, generator_id: str, day: date) -> dict[str, Any]:
        """Push the reading of ``day`` to mindergas.nl (token from options)."""
        token = self.entry.options.get(OPT_INTEGRATIONS, {}).get(CONF_MINDERGAS_TOKEN)
        if not token:
            raise HomeAssistantError("No mindergas.nl API token configured in the options")
        reading = await self.async_meter_reading(generator_id, day)
        status = await async_push_reading(async_get_clientsession(self.hass), token, day, reading)
        return {"date": day.isoformat(), "reading": round(reading, 3), "status": status}

    async def _async_daily_mindergas_push(self) -> None:
        """Push today's reading to mindergas.nl when the daily push is enabled."""
        integrations = self.entry.options.get(OPT_INTEGRATIONS, {})
        if not integrations.get(CONF_MINDERGAS_DAILY_PUSH):
            return
        generator_id = integrations.get(CONF_MINDERGAS_GENERATOR)
        if not generator_id:
            return
        try:
            await self.async_push_reading(generator_id, self.today)
        except (MindergasError, HomeAssistantError) as err:
            _LOGGER.warning("Daily mindergas.nl push failed: %s", err)

    def summary(self) -> dict[str, Any]:
        """Return a compact summary without entity ids or tokens (diagnostics)."""
        return {
            "site_id": self.site_id,
            "generators": [
                {
                    "id": generator.generator_id,
                    "kind": generator.kind,
                    "role": generator.role,
                    "conversion_mode": generator.conversion_mode,
                    "dhw_mode": generator.dhw_mode,
                }
                for generator in self.generators
            ],
            "measures": [
                {
                    "id": measure.measure_id,
                    "date": measure.date.isoformat(),
                    "category": measure.category,
                }
                for measure in self.measures
            ],
            "rooms": [
                {
                    "id": room.room_id,
                    "demand_kind": room.demand_kind,
                    "emitter_kind": room.emitter_kind,
                    "enabled": room.enabled,
                }
                for room in self.rooms
            ],
            "methods": method_options(self.entry),
            "history": history_options(self.entry),
            "backfill_progress": self.backfill_progress,
            "last_run": self.store.get_meta(META_LAST_RUN),
            "last_definitive_date": self.store.get_meta(META_LAST_DEFINITIVE_DATE),
        }
