"""Open-Meteo client: ERA5 archive plus forecast ``past_days`` for recent days.

Hourly values (``temperature_2m``, ``wind_speed_10m`` in m/s, ``shortwave_radiation``
in W/m2) are aggregated to local calendar days (the API returns local time when
``timezone`` is passed):

- ``t_mean`` = mean, ``t_min``/``t_max`` = min/max of the hourly temperatures
- ``wind_mean`` = mean hourly wind speed
- ``radiation`` = sum of hourly W/m2 x 1 h = Wh/m2, x 0.36 = J/cm2

Days with fewer than 20 valid hourly temperatures are skipped; days with some missing
hours are kept but marked provisional. Everything from the forecast API is provisional
(model data instead of reanalysis). Only :func:`fetch_daily` touches the network.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from ..constants import KMH_TO_MS, MJ_M2_TO_J_CM2, WH_M2_TO_J_CM2
from ..models import DailyWeather

_LOGGER = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS: tuple[str, ...] = ("temperature_2m", "wind_speed_10m", "shortwave_radiation")
#: Minimum number of valid hourly temperatures for a day to be used.
MIN_HOURS_PER_DAY = 20
#: Days older than this are requested from the archive (ERA5) API.
ARCHIVE_DELAY_DAYS = 8
#: Maximum ``past_days`` of the forecast API.
MAX_PAST_DAYS = 92
DEFAULT_TIMEOUT_S = 30


def _common_params(latitude: float, longitude: float, timezone: str) -> dict[str, Any]:
    return {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "ms",
        "timezone": timezone,
    }


def build_archive_url(
    latitude: float, longitude: float, start: date, end: date, timezone: str
) -> str:
    """URL of the ERA5 archive request for ``start``..``end`` (inclusive)."""
    params = _common_params(latitude, longitude, timezone)
    params["start_date"] = start.isoformat()
    params["end_date"] = end.isoformat()
    return f"{ARCHIVE_URL}?{urlencode(params, safe=',/')}"


def build_forecast_url(
    latitude: float, longitude: float, past_days: int, timezone: str, forecast_days: int = 1
) -> str:
    """URL of the forecast request covering the last ``past_days`` days (plus today)."""
    params = _common_params(latitude, longitude, timezone)
    params["past_days"] = str(max(0, min(past_days, MAX_PAST_DAYS)))
    params["forecast_days"] = str(forecast_days)
    return f"{FORECAST_URL}?{urlencode(params, safe=',/')}"


def _source(payload: dict[str, Any]) -> str:
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    if latitude is None or longitude is None:
        return "open_meteo"
    return f"open_meteo:{float(latitude):.2f},{float(longitude):.2f}"


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def parse_open_meteo_hourly(
    payload: dict[str, Any], provisional: bool = False
) -> list[DailyWeather]:
    """Aggregate an Open-Meteo hourly payload into daily weather (see module docstring)."""
    hourly = payload.get("hourly") or {}
    times: list[str] = hourly.get("time") or []
    temps: list[float | None] = hourly.get("temperature_2m") or []
    winds: list[float | None] = hourly.get("wind_speed_10m") or []
    radiation: list[float | None] = hourly.get("shortwave_radiation") or []
    units = payload.get("hourly_units") or {}
    wind_factor = KMH_TO_MS if str(units.get("wind_speed_10m", "m/s")).lower() == "km/h" else 1.0
    source = _source(payload)

    days: dict[date, dict[str, list[float]]] = {}
    hours_per_day: dict[date, int] = {}
    for index, stamp in enumerate(times):
        day = date.fromisoformat(stamp[:10])
        bucket = days.setdefault(day, {"t": [], "w": [], "q": []})
        hours_per_day[day] = hours_per_day.get(day, 0) + 1
        temperature = temps[index] if index < len(temps) else None
        if temperature is not None:
            bucket["t"].append(float(temperature))
        wind = winds[index] if index < len(winds) else None
        if wind is not None:
            bucket["w"].append(float(wind) * wind_factor)
        rad = radiation[index] if index < len(radiation) else None
        if rad is not None:
            bucket["q"].append(float(rad))

    result: list[DailyWeather] = []
    for day in sorted(days):
        bucket = days[day]
        n_valid = len(bucket["t"])
        if n_valid < MIN_HOURS_PER_DAY:
            _LOGGER.debug("Open-Meteo %s: only %d hourly values, day skipped", day, n_valid)
            continue
        partial = n_valid < hours_per_day[day] or (
            bool(bucket["w"]) and len(bucket["w"]) < hours_per_day[day]
        )
        result.append(
            DailyWeather(
                date=day,
                t_mean=round(_mean(bucket["t"]), 3),
                wind_mean=round(_mean(bucket["w"]), 3) if bucket["w"] else None,
                radiation=round(sum(bucket["q"]) * WH_M2_TO_J_CM2, 1) if bucket["q"] else None,
                t_min=min(bucket["t"]),
                t_max=max(bucket["t"]),
                provisional=provisional or partial,
                source=source,
            )
        )
    return result


def parse_open_meteo_daily(
    payload: dict[str, Any], provisional: bool = False
) -> list[DailyWeather]:
    """Parse an Open-Meteo ``daily`` payload (``temperature_2m_mean``, ``wind_speed_10m_mean``,
    ``shortwave_radiation_sum`` in MJ/m2, ``temperature_2m_min/max``)."""
    daily = payload.get("daily") or {}
    times: list[str] = daily.get("time") or []
    units = payload.get("daily_units") or {}
    wind_factor = (
        KMH_TO_MS if str(units.get("wind_speed_10m_mean", "m/s")).lower() == "km/h" else 1.0
    )
    source = _source(payload)

    def value(name: str, index: int) -> float | None:
        values = daily.get(name) or []
        item = values[index] if index < len(values) else None
        return None if item is None else float(item)

    result: list[DailyWeather] = []
    for index, stamp in enumerate(times):
        t_mean = value("temperature_2m_mean", index)
        if t_mean is None:
            continue
        wind = value("wind_speed_10m_mean", index)
        rad = value("shortwave_radiation_sum", index)
        result.append(
            DailyWeather(
                date=date.fromisoformat(stamp[:10]),
                t_mean=t_mean,
                wind_mean=None if wind is None else wind * wind_factor,
                radiation=None if rad is None else rad * MJ_M2_TO_J_CM2,
                t_min=value("temperature_2m_min", index),
                t_max=value("temperature_2m_max", index),
                provisional=provisional,
                source=source,
            )
        )
    return result


async def fetch_json(
    session: Any, url: str, timeout_s: float = DEFAULT_TIMEOUT_S
) -> dict[str, Any]:
    """GET ``url`` with an injected ``aiohttp.ClientSession`` and return the JSON body."""
    kwargs: dict[str, Any] = {}
    try:
        import aiohttp  # optional dependency, imported lazily

        kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout_s)
    except ImportError:  # pragma: no cover - exercised only without aiohttp
        pass
    async with session.get(url, **kwargs) as response:
        response.raise_for_status()
        return await response.json()


class OpenMeteoClient:
    """Async client for one location; the aiohttp session is injected (ADR 0002)."""

    def __init__(
        self, latitude: float, longitude: float, timezone: str = "Europe/Amsterdam"
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone

    async def fetch_daily(
        self, start: date, end: date, session: Any, today: date | None = None
    ) -> list[DailyWeather]:
        """Fetch ``start``..``end`` combining archive and forecast APIs."""
        return await fetch_daily(
            start, end, session, self.latitude, self.longitude, self.timezone, today=today
        )


async def fetch_daily(
    start: date,
    end: date,
    session: Any,
    latitude: float,
    longitude: float,
    timezone: str = "Europe/Amsterdam",
    today: date | None = None,
) -> list[DailyWeather]:
    """Fetch daily weather: archive API for days older than 7 days (definitive), forecast
    API with ``past_days`` for recent days (provisional). Days missing from the archive
    (ERA5 delay) are filled from the forecast API when within its ``past_days`` reach.
    """
    today = today or date.today()
    end = min(end, today)
    if end < start:
        return []
    result: dict[date, DailyWeather] = {}

    archive_end = min(end, today - timedelta(days=ARCHIVE_DELAY_DAYS))
    if start <= archive_end:
        url = build_archive_url(latitude, longitude, start, archive_end, timezone)
        payload = await fetch_json(session, url)
        for weather in parse_open_meteo_hourly(payload, provisional=False):
            result[weather.date] = weather

    recent_start = max(start, archive_end + timedelta(days=1))
    # Fill the ERA5 gap: earliest missing archive day within the forecast API's reach.
    earliest_reach = today - timedelta(days=MAX_PAST_DAYS)
    day = max(start, earliest_reach)
    while day <= archive_end:
        if day not in result:
            recent_start = min(recent_start, day)
            break
        day += timedelta(days=1)

    if recent_start <= end:
        past_days = (today - recent_start).days
        url = build_forecast_url(latitude, longitude, past_days, timezone)
        payload = await fetch_json(session, url)
        for weather in parse_open_meteo_hourly(payload, provisional=True):
            if recent_start <= weather.date <= end and weather.date not in result:
                result[weather.date] = weather

    _LOGGER.debug("Open-Meteo: %d days fetched for %s..%s", len(result), start, end)
    return [result[day] for day in sorted(result)]


class OpenMeteoProvider:
    """:class:`WeatherProvider` implementation with a bound session (ARCHITECTURE section 10)."""

    def __init__(
        self,
        session: Any,
        latitude: float,
        longitude: float,
        timezone: str = "Europe/Amsterdam",
    ) -> None:
        self.session = session
        self.client = OpenMeteoClient(latitude, longitude, timezone)

    async def fetch_daily(self, start: date, end: date) -> list[DailyWeather]:
        """Fetch ``start``..``end`` for the configured location."""
        return await self.client.fetch_daily(start, end, self.session)
