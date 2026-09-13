"""Open-Meteo client: URL builders, hourly aggregation, archive/forecast split."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from heatprint_core.weather.open_meteo import (
    ARCHIVE_URL,
    FORECAST_URL,
    OpenMeteoClient,
    OpenMeteoProvider,
    build_archive_url,
    build_forecast_url,
    parse_open_meteo_daily,
    parse_open_meteo_hourly,
)


def _hourly_payload(
    days: list[date], temps: list[float], wind: float, radiation: float
) -> dict[str, Any]:
    """Payload with the same 24 hourly temperatures on every day."""
    times: list[str] = []
    t_values: list[float | None] = []
    w_values: list[float | None] = []
    q_values: list[float | None] = []
    for day in days:
        for hour in range(24):
            times.append(f"{day.isoformat()}T{hour:02d}:00")
            t_values.append(temps[hour])
            w_values.append(wind)
            q_values.append(radiation if 8 <= hour < 16 else 0.0)
    return {
        "latitude": 50.875,
        "longitude": 5.99,
        "timezone": "Europe/Amsterdam",
        "hourly_units": {
            "temperature_2m": "°C",
            "wind_speed_10m": "m/s",
            "shortwave_radiation": "W/m²",
        },
        "hourly": {
            "time": times,
            "temperature_2m": t_values,
            "wind_speed_10m": w_values,
            "shortwave_radiation": q_values,
        },
    }


def test_archive_url() -> None:
    url = build_archive_url(50.89, 5.98, date(2025, 1, 1), date(2025, 1, 31), "Europe/Amsterdam")
    parsed = urlparse(url)
    assert url.startswith(ARCHIVE_URL)
    query = parse_qs(parsed.query)
    assert query["hourly"] == ["temperature_2m,wind_speed_10m,shortwave_radiation"]
    assert query["wind_speed_unit"] == ["ms"]
    assert query["timezone"] == ["Europe/Amsterdam"]
    assert query["start_date"] == ["2025-01-01"] and query["end_date"] == ["2025-01-31"]
    assert query["latitude"] == ["50.8900"]


def test_forecast_url() -> None:
    url = build_forecast_url(50.89, 5.98, past_days=10, timezone="Europe/Amsterdam")
    assert url.startswith(FORECAST_URL)
    query = parse_qs(urlparse(url).query)
    assert query["past_days"] == ["10"] and query["forecast_days"] == ["1"]
    assert parse_qs(urlparse(build_forecast_url(1, 2, 500, "UTC")).query)["past_days"] == ["92"]


def test_hourly_aggregation() -> None:
    temps = [float(h % 12) for h in range(24)]  # 0..11 twice: mean 5.5, min 0, max 11
    payload = _hourly_payload(
        [date(2026, 1, 10), date(2026, 1, 11)], temps, wind=3.0, radiation=250.0
    )
    days = parse_open_meteo_hourly(payload, provisional=False)
    assert [d.date for d in days] == [date(2026, 1, 10), date(2026, 1, 11)]
    first = days[0]
    assert first.t_mean == pytest.approx(5.5)
    assert first.t_min == 0.0 and first.t_max == 11.0
    assert first.wind_mean == pytest.approx(3.0)
    # 8 hours x 250 W/m2 = 2000 Wh/m2 = 720 J/cm2
    assert first.radiation == pytest.approx(2000 * 0.36)
    assert first.source == "open_meteo:50.88,5.99"
    assert first.provisional is False
    assert parse_open_meteo_hourly(payload, provisional=True)[0].provisional is True


def test_hourly_partial_and_short_days() -> None:
    temps = [5.0] * 24
    payload = _hourly_payload([date(2026, 1, 10), date(2026, 1, 11)], temps, 2.0, 0.0)
    values = payload["hourly"]["temperature_2m"]
    # Day 1: two missing hours -> kept but provisional. Day 2: only 19 values -> skipped.
    values[3] = None
    values[4] = None
    for index in range(24 + 19, 48):
        values[index] = None
    days = parse_open_meteo_hourly(payload)
    assert len(days) == 1
    assert days[0].provisional is True
    assert days[0].t_mean == 5.0


def test_hourly_wind_in_kmh_converted() -> None:
    payload = _hourly_payload([date(2026, 1, 10)], [5.0] * 24, wind=36.0, radiation=0.0)
    payload["hourly_units"]["wind_speed_10m"] = "km/h"
    assert parse_open_meteo_hourly(payload)[0].wind_mean == pytest.approx(10.0)


def test_daily_payload() -> None:
    payload = {
        "latitude": 50.875,
        "longitude": 5.99,
        "daily_units": {"wind_speed_10m_mean": "km/h"},
        "daily": {
            "time": ["2026-01-10", "2026-01-11"],
            "temperature_2m_mean": [3.5, None],
            "temperature_2m_min": [0.5, None],
            "temperature_2m_max": [6.0, None],
            "wind_speed_10m_mean": [18.0, None],
            "shortwave_radiation_sum": [1.8, None],
        },
    }
    days = parse_open_meteo_daily(payload)
    assert len(days) == 1
    assert days[0].wind_mean == pytest.approx(5.0)
    assert days[0].radiation == pytest.approx(180.0)
    assert days[0].t_max == 6.0


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, today: date) -> None:
        self.urls: list[str] = []
        self.today = today

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.urls.append(url)
        query = parse_qs(urlparse(url).query)
        if url.startswith(ARCHIVE_URL):
            start = date.fromisoformat(query["start_date"][0])
            end = date.fromisoformat(query["end_date"][0])
        else:
            past = int(query["past_days"][0])
            start = self.today - timedelta(days=past)
            end = self.today
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        return _FakeResponse(_hourly_payload(days, [4.0] * 24, 3.0, 100.0))


async def test_fetch_daily_combines_archive_and_forecast() -> None:
    today = date(2026, 3, 15)
    session = _FakeSession(today)
    client = OpenMeteoClient(50.89, 5.98, "Europe/Amsterdam")
    start, end = date(2026, 2, 1), date(2026, 3, 14)
    days = await client.fetch_daily(start, end, session, today=today)
    assert [d.date for d in days][0] == start and days[-1].date == end
    assert len(days) == (end - start).days + 1
    assert len(session.urls) == 2
    archive_query = parse_qs(urlparse(session.urls[0]).query)
    assert archive_query["end_date"] == ["2026-03-07"]  # today - 8 days
    forecast_query = parse_qs(urlparse(session.urls[1]).query)
    assert forecast_query["past_days"] == ["7"]
    definitive = [d for d in days if not d.provisional]
    provisional = [d for d in days if d.provisional]
    assert definitive[-1].date == date(2026, 3, 7)
    assert provisional[0].date == date(2026, 3, 8) and len(provisional) == 7


async def test_fetch_daily_archive_only() -> None:
    today = date(2026, 3, 15)
    session = _FakeSession(today)
    days = await OpenMeteoClient(50.89, 5.98).fetch_daily(
        date(2025, 1, 1), date(2025, 1, 10), session, today=today
    )
    assert len(days) == 10 and len(session.urls) == 1
    assert all(not d.provisional for d in days)


async def test_provider_binds_session() -> None:
    session = _FakeSession(date(2026, 3, 15))
    provider = OpenMeteoProvider(session, 50.89, 5.98)
    days = await provider.fetch_daily(date(2025, 1, 1), date(2025, 1, 3))
    assert len(days) == 3 and len(session.urls) == 1
