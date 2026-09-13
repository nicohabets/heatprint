"""Persistent JSON store for Heatprint (climatology, fits, baselines, flags, cache).

The day metrics themselves live in the recorder as external long-term statistics
(see statistics_writer). This store keeps the small structured data described in
DATA_MODEL 2.2: climatology, the last signature fits, DHW baselines, the latest
forecast, per-day data quality flags (compact bitmask) and a weather cache of the
last 400 days. Imported meter readings (CSV) are kept as daily consumption so the
pipeline can use them for days before the Home Assistant history starts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    FLAG_BITS,
    FLAG_NAMES,
    MAX_STORED_FITS,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
    WEATHER_CACHE_DAYS,
)
from .core_api import WeatherDay

SAVE_DELAY_SECONDS = 10

KEY_META = "meta"
KEY_CLIMATOLOGY = "climatology"
KEY_FITS = "fits"
KEY_BASELINES = "baselines"
KEY_FORECAST = "forecast"
KEY_FLAGS = "flags"
KEY_WEATHER_CACHE = "weather_cache"
KEY_IMPORTED = "imported"

META_WEATHER_SIGNATURE = "weather_signature"
META_LAST_DEFINITIVE_DATE = "last_definitive_date"
META_LAST_RUN = "last_run"
META_LAST_FIT_AT = "last_fit_at"
META_BACKFILL_DONE = "backfill_done"
META_RECOMPUTE_MARKER = "recompute_marker"
META_CLIMATOLOGY_SIGNATURE = "climatology_signature"


def _empty_data() -> dict[str, Any]:
    return {
        KEY_META: {},
        KEY_CLIMATOLOGY: None,
        KEY_FITS: [],
        KEY_BASELINES: {},
        KEY_FORECAST: None,
        KEY_FLAGS: {},
        KEY_WEATHER_CACHE: {},
        KEY_IMPORTED: {},
    }


def flags_to_bits(flags: Iterable[str]) -> int:
    """Encode flag names as a bitmask (unknown names are ignored)."""
    bits = 0
    for flag in flags:
        bits |= FLAG_BITS.get(flag, 0)
    return bits


def bits_to_flags(bits: int) -> list[str]:
    """Decode a bitmask into flag names."""
    return [name for name in FLAG_NAMES if bits & FLAG_BITS[name]]


class HeatprintStore:
    """Wrapper around homeassistant.helpers.storage.Store for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the store for a config entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_TEMPLATE.format(entry_id=entry_id)
        )
        self._data: dict[str, Any] = _empty_data()

    async def async_load(self) -> None:
        """Load the store from disk."""
        loaded = await self._store.async_load()
        data = _empty_data()
        if loaded:
            data.update(loaded)
        self._data = data

    async def async_save(self) -> None:
        """Write the store to disk now."""
        await self._store.async_save(self._data)

    @callback
    def async_delay_save(self) -> None:
        """Schedule a delayed write of the store."""
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY_SECONDS)

    async def async_remove(self) -> None:
        """Remove the store file (config entry removed)."""
        await self._store.async_remove()

    @property
    def data(self) -> dict[str, Any]:
        """Return the raw store data (read-only use, e.g. diagnostics)."""
        return self._data

    # --- meta ---------------------------------------------------------------------

    def get_meta(self, key: str, default: Any = None) -> Any:
        """Return a meta value."""
        return self._data[KEY_META].get(key, default)

    def set_meta(self, key: str, value: Any) -> None:
        """Set a meta value."""
        self._data[KEY_META][key] = value

    def get_meta_date(self, key: str) -> date | None:
        """Return a meta value stored as ISO date."""
        value = self.get_meta(key)
        return date.fromisoformat(value) if value else None

    def set_meta_date(self, key: str, value: date | None) -> None:
        """Store a date as ISO string in meta."""
        self.set_meta(key, value.isoformat() if value else None)

    # --- climatology ---------------------------------------------------------------

    @property
    def climatology(self) -> dict[str, Any] | None:
        """Return the stored climatology (dict form of core Climatology)."""
        return self._data[KEY_CLIMATOLOGY]

    def set_climatology(self, climatology: Mapping[str, Any] | None) -> None:
        """Store the climatology."""
        self._data[KEY_CLIMATOLOGY] = dict(climatology) if climatology else None

    # --- fits ----------------------------------------------------------------------

    @property
    def fits(self) -> list[dict[str, Any]]:
        """Return the stored fits, newest last."""
        return list(self._data[KEY_FITS])

    @property
    def latest_fit(self) -> dict[str, Any] | None:
        """Return the most recent fit or None."""
        fits = self._data[KEY_FITS]
        return dict(fits[-1]) if fits else None

    def add_fit(self, fit: Mapping[str, Any]) -> None:
        """Add a fit, replacing an existing fit for the same period and preset."""
        key = (fit.get("period_start"), fit.get("period_end"), fit.get("tac_preset"))
        fits = [
            existing
            for existing in self._data[KEY_FITS]
            if (
                existing.get("period_start"),
                existing.get("period_end"),
                existing.get("tac_preset"),
            )
            != key
        ]
        fits.append(dict(fit))
        self._data[KEY_FITS] = fits[-MAX_STORED_FITS:]

    # --- baselines -----------------------------------------------------------------

    @property
    def baselines(self) -> dict[str, float]:
        """Return the DHW baseline per generator (carrier units per day)."""
        return dict(self._data[KEY_BASELINES])

    def set_baselines(self, baselines: Mapping[str, float]) -> None:
        """Store the DHW baselines."""
        self._data[KEY_BASELINES] = dict(baselines)

    # --- forecast ------------------------------------------------------------------

    @property
    def forecast(self) -> dict[str, Any] | None:
        """Return the latest forecast."""
        return self._data[KEY_FORECAST]

    def set_forecast(self, forecast: Mapping[str, Any] | None) -> None:
        """Store the latest forecast."""
        self._data[KEY_FORECAST] = dict(forecast) if forecast else None

    # --- flags ---------------------------------------------------------------------

    def set_flags(self, day: date, flags: Iterable[str]) -> None:
        """Store the data quality flags of one day (compact bitmask)."""
        bits = flags_to_bits(flags)
        key = day.isoformat()
        if bits:
            self._data[KEY_FLAGS][key] = bits
        else:
            self._data[KEY_FLAGS].pop(key, None)

    def get_flags(self, day: date) -> list[str]:
        """Return the flags of one day."""
        return bits_to_flags(int(self._data[KEY_FLAGS].get(day.isoformat(), 0)))

    def flags_between(self, start: date, end: date) -> dict[date, list[str]]:
        """Return the flags of all days in start..end that have any flag set."""
        result: dict[date, list[str]] = {}
        for key, bits in self._data[KEY_FLAGS].items():
            day = date.fromisoformat(key)
            if start <= day <= end and bits:
                result[day] = bits_to_flags(int(bits))
        return result

    def flag_counts(self, start: date, end: date) -> dict[str, int]:
        """Return how often each flag occurs in start..end."""
        counts: dict[str, int] = {}
        for flags in self.flags_between(start, end).values():
            for flag in flags:
                counts[flag] = counts.get(flag, 0) + 1
        return counts

    # --- weather cache -------------------------------------------------------------

    def update_weather_cache(self, days: Iterable[WeatherDay]) -> None:
        """Merge weather days into the cache and trim it to the last 400 days."""
        cache = self._data[KEY_WEATHER_CACHE]
        for day in days:
            cache[day.date.isoformat()] = day.to_store()
        if cache:
            newest = max(cache)
            cutoff = (date.fromisoformat(newest) - timedelta(days=WEATHER_CACHE_DAYS)).isoformat()
            for key in [key for key in cache if key < cutoff]:
                del cache[key]

    def cached_weather(self, start: date, end: date) -> dict[date, WeatherDay]:
        """Return cached weather days in start..end."""
        result: dict[date, WeatherDay] = {}
        for key, value in self._data[KEY_WEATHER_CACHE].items():
            day = date.fromisoformat(key)
            if start <= day <= end:
                result[day] = WeatherDay.from_store(day, value)
        return result

    def clear_weather_cache(self) -> None:
        """Drop the weather cache (weather source changed)."""
        self._data[KEY_WEATHER_CACHE] = {}

    # --- imported daily consumption (CSV) ------------------------------------------

    def set_imported(self, generator_id: str, consumption: Mapping[date, float]) -> None:
        """Merge imported daily consumption for one generator."""
        target = self._data[KEY_IMPORTED].setdefault(generator_id, {})
        for day, value in consumption.items():
            target[day.isoformat()] = value

    def imported(self, generator_id: str, start: date, end: date) -> dict[date, float]:
        """Return imported daily consumption for one generator in start..end."""
        result: dict[date, float] = {}
        for key, value in self._data[KEY_IMPORTED].get(generator_id, {}).items():
            day = date.fromisoformat(key)
            if start <= day <= end:
                result[day] = float(value)
        return result

    def imported_range(self, generator_id: str) -> tuple[date, date] | None:
        """Return the first and last imported day of a generator."""
        keys = self._data[KEY_IMPORTED].get(generator_id, {})
        if not keys:
            return None
        return date.fromisoformat(min(keys)), date.fromisoformat(max(keys))
