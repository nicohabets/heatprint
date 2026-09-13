"""KNMI daggegevens client: form body, parsing, chunking, fetch with a fake session."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from heatprint_core.weather.knmi import (
    KNMI_DAILY_URL,
    KnmiClient,
    KnmiProvider,
    build_form_body,
    chunk_date_range,
    encode_form_body,
    parse_knmi_daggegevens,
)

SAMPLE = """# BRON: KONINKLIJK NEDERLANDS METEOROLOGISCH INSTITUUT (KNMI)
# Opmerking: door stationsverplaatsingen en veranderingen in waarneemmethodieken zijn deze tijdreeksen van dagwaarden mogelijk inhomogeen!
#
#
# STN      LON(east)   LAT(north)     ALT(m)  NAME
# 380:         5.762       50.906      114.30  MAASTRICHT
#
# YYYYMMDD : datum (YYYY=jaar MM=maand DD=dag) / date (YYYY=year MM=month DD=day)
# TG       : Etmaalgemiddelde temperatuur (in 0.1 graden Celsius) / Daily mean temperature in (0.1 degrees Celsius)
# FG       : Etmaalgemiddelde windsnelheid (in 0.1 m/s) / Daily mean windspeed (in 0.1 m/s)
# Q        : Globale straling (in J/cm2) / Global radiation (in J/cm2)
# TN       : Minimum temperatuur (in 0.1 graden Celsius) / Minimum temperature (in 0.1 degrees Celsius)
# TX       : Maximum temperatuur (in 0.1 graden Celsius) / Maximum temperature (in 0.1 degrees Celsius)
#
# STN,YYYYMMDD,   TG,   FG,    Q,   TN,   TX
#
  380,20260110,   35,   42,  180,    5,   60
  380,20260111,  -12,     ,  250,  -50,   21
  380,20260112,     ,   30,  100,  -10,   20
  380,20260113,   80,   55,     ,   40,  120
"""


def test_form_body() -> None:
    fields = build_form_body(date(2026, 1, 1), date(2026, 1, 31), 380)
    assert fields == {
        "start": "20260101",
        "end": "20260131",
        "stns": "380",
        "vars": "TG:FG:Q:TN:TX",
    }
    assert encode_form_body(fields) == "start=20260101&end=20260131&stns=380&vars=TG:FG:Q:TN:TX"
    assert build_form_body(date(2026, 1, 1), date(2026, 1, 2), "260")["stns"] == "260"


def test_parse_sample() -> None:
    days = parse_knmi_daggegevens(SAMPLE, requested_end=date(2026, 1, 13))
    assert [d.date for d in days] == [date(2026, 1, 10), date(2026, 1, 11), date(2026, 1, 13)]
    first = days[0]
    assert first.t_mean == pytest.approx(3.5)
    assert first.wind_mean == pytest.approx(4.2)
    assert first.radiation == 180.0
    assert first.t_min == pytest.approx(0.5)
    assert first.t_max == pytest.approx(6.0)
    assert first.source == "knmi:380"
    assert first.provisional is False
    # Blank FG becomes None, negative tenths convert correctly.
    assert days[1].wind_mean is None
    assert days[1].t_mean == pytest.approx(-1.2)
    assert days[1].t_min == pytest.approx(-5.0)
    # Blank Q becomes None; the day matching the requested end is provisional.
    assert days[2].radiation is None
    assert days[2].provisional is True


def test_parse_provisional_window_defaults_to_last_day() -> None:
    days = parse_knmi_daggegevens(SAMPLE, provisional_days=2)
    assert [d.provisional for d in days] == [False, False, True]
    assert all(not d.provisional for d in parse_knmi_daggegevens(SAMPLE, provisional_days=0))


def test_parse_header_without_hash_and_empty_text() -> None:
    text = "STN,YYYYMMDD,TG\n260,20260201,-5\n"
    days = parse_knmi_daggegevens(text)
    assert len(days) == 1 and days[0].t_mean == -0.5 and days[0].source == "knmi:260"
    assert parse_knmi_daggegevens("") == []
    assert parse_knmi_daggegevens("# only comments\n") == []


def test_chunk_date_range() -> None:
    chunks = chunk_date_range(date(2024, 1, 1), date(2025, 12, 31), max_days=366)
    assert chunks[0] == (date(2024, 1, 1), date(2024, 12, 31))
    assert chunks[1] == (date(2025, 1, 1), date(2025, 12, 31))
    assert len(chunks) == 2
    assert chunk_date_range(date(2026, 1, 1), date(2026, 1, 1)) == [
        (date(2026, 1, 1), date(2026, 1, 1))
    ]
    assert chunk_date_range(date(2026, 1, 2), date(2026, 1, 1)) == []


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, text: str) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._text = text

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((url, kwargs))
        return _FakeResponse(self._text)


async def test_fetch_daily_posts_form_and_parses() -> None:
    session = _FakeSession(SAMPLE)
    client = KnmiClient(380)
    days = await client.fetch_daily(date(2026, 1, 10), date(2026, 1, 13), session)
    assert len(days) == 3
    url, kwargs = session.calls[0]
    assert url == KNMI_DAILY_URL
    assert kwargs["data"] == "start=20260110&end=20260113&stns=380&vars=TG:FG:Q:TN:TX"
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert days[-1].provisional is True


async def test_fetch_daily_chunks_long_ranges() -> None:
    session = _FakeSession(SAMPLE)
    await KnmiClient("380").fetch_daily(date(2023, 1, 1), date(2025, 6, 30), session)
    assert len(session.calls) == 3
    assert session.calls[0][1]["data"].startswith("start=20230101&end=20240101")
    assert session.calls[1][1]["data"].startswith("start=20240102&end=20250101")
    assert session.calls[2][1]["data"].startswith("start=20250102&end=20250630")


async def test_provider_binds_session() -> None:
    from heatprint_core.weather.base import WeatherProvider

    session = _FakeSession(SAMPLE)
    provider = KnmiProvider(session, "380")
    assert isinstance(provider, WeatherProvider)
    days = await provider.fetch_daily(date(2026, 1, 10), date(2026, 1, 13))
    assert len(days) == 3 and session.calls[0][1]["data"].endswith("stns=380&vars=TG:FG:Q:TN:TX")
