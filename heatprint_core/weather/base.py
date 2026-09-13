"""Weather provider interface and merge rules (METHODS section 2).

A provider delivers one :class:`DailyWeather` per local calendar day. Recent days may
be ``provisional`` (KNMI: last 1-2 days, Open-Meteo: model data from the forecast API)
and are overwritten by a later, definitive fetch.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Protocol, runtime_checkable

from ..models import DailyWeather


@runtime_checkable
class WeatherProvider(Protocol):
    """Anything that can fetch daily weather for a date range (ARCHITECTURE section 10)."""

    async def fetch_daily(self, start: date, end: date) -> list[DailyWeather]:
        """Return the daily weather for ``start``..``end`` inclusive (may be incomplete)."""
        ...


def merge_weather(
    existing: Iterable[DailyWeather] | Mapping[date, DailyWeather],
    new: Iterable[DailyWeather] | Mapping[date, DailyWeather],
) -> dict[date, DailyWeather]:
    """Merge two weather sets; a new value replaces an existing one unless the existing
    value is definitive and the new one is provisional.

    Returns a dict keyed by date, sorted by date.
    """
    result: dict[date, DailyWeather] = {}
    for weather in _values(existing):
        result[weather.date] = weather
    for weather in _values(new):
        current = result.get(weather.date)
        if current is not None and not current.provisional and weather.provisional:
            continue
        result[weather.date] = weather
    return dict(sorted(result.items()))


def _values(
    data: Iterable[DailyWeather] | Mapping[date, DailyWeather],
) -> Iterable[DailyWeather]:
    if isinstance(data, Mapping):
        return data.values()
    return data


def weather_by_date(weathers: Iterable[DailyWeather]) -> dict[date, DailyWeather]:
    """Index a list of daily weather by date (later entries win)."""
    return merge_weather((), weathers)
