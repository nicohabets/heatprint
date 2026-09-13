"""KNMI daily station data ("daggegevens") client (METHODS section 2, ARCHITECTURE section 6).

The KNMI script API takes a POST form (``start``, ``end``, ``stns``, ``vars``) and
returns CSV with a comment header. The variables used here:

- ``TG`` daily mean temperature (0.1 degrees C), ``TN``/``TX`` min/max (0.1 degrees C)
- ``FG`` daily mean wind speed (0.1 m/s)
- ``Q`` global radiation (J/cm2)

Only :func:`fetch_daily` touches the network; parsing is pure and testable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

from ..constants import KNMI_TENTHS
from ..models import DailyWeather

_LOGGER = logging.getLogger(__name__)

KNMI_DAILY_URL = "https://www.daggegevens.knmi.nl/klimatologie/daggegevens"
DEFAULT_VARS: tuple[str, ...] = ("TG", "FG", "Q", "TN", "TX")
#: Variables reported in tenths of a unit.
TENTHS_VARS: frozenset[str] = frozenset({"TG", "TN", "TX", "FG", "FHX", "FHN", "FXX", "T10N"})
#: Maximum number of days per request when backfilling.
MAX_DAYS_PER_REQUEST = 366
DEFAULT_TIMEOUT_S = 30


def build_form_body(
    start: date, end: date, station: int | str, variables: Sequence[str] = DEFAULT_VARS
) -> dict[str, str]:
    """Form fields for the KNMI daggegevens POST request."""
    return {
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "stns": str(int(station)),
        "vars": ":".join(variables),
    }


def encode_form_body(fields: dict[str, str]) -> str:
    """Encode the form fields as ``start=...&end=...&stns=380&vars=TG:FG:Q:TN:TX``."""
    return "&".join(f"{key}={value}" for key, value in fields.items())


def chunk_date_range(
    start: date, end: date, max_days: int = MAX_DAYS_PER_REQUEST
) -> list[tuple[date, date]]:
    """Split ``start``..``end`` (inclusive) into consecutive chunks of at most ``max_days``."""
    if end < start:
        return []
    chunks: list[tuple[date, date]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(end, chunk_start + timedelta(days=max_days - 1))
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


def _parse_value(name: str, text: str) -> float | None:
    text = text.strip()
    if text == "":
        return None
    value = float(text)
    if name in TENTHS_VARS:
        return round(value * KNMI_TENTHS, 3)
    return value


def parse_knmi_daggegevens(
    text: str, requested_end: date | None = None, provisional_days: int = 1
) -> list[DailyWeather]:
    """Parse the CSV text of the KNMI daggegevens API into daily weather.

    Handles the comment header (lines starting with ``#``), the column header line
    (``# STN,YYYYMMDD,   TG,...`` - itself a comment line), blank values and the
    tenths conversion of TG/FG/TN/TX. Days without ``TG`` are skipped. The last
    ``provisional_days`` days up to ``requested_end`` (default: the last day in the
    data) are marked provisional. ``source`` becomes ``"knmi:<station>"``.
    """
    columns: list[str] | None = None
    rows: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        body = line.lstrip("#").strip()
        if body.startswith("STN") and "YYYYMMDD" in body and "," in body:
            columns = [c.strip().upper() for c in body.split(",")]
            continue
        if line.startswith("#"):
            continue
        if columns is None:
            _LOGGER.debug("KNMI data line before header ignored: %s", line)
            continue
        values = [v.strip() for v in line.split(",")]
        if len(values) != len(columns):
            _LOGGER.debug(
                "KNMI line with %d values for %d columns ignored", len(values), len(columns)
            )
            continue
        rows.append(dict(zip(columns, values, strict=True)))

    result: list[DailyWeather] = []
    for row in rows:
        try:
            day = datetime.strptime(row["YYYYMMDD"], "%Y%m%d").date()
        except (KeyError, ValueError):
            continue
        t_mean = _parse_value("TG", row.get("TG", ""))
        if t_mean is None:
            _LOGGER.debug("KNMI %s: no TG, day skipped", day)
            continue
        result.append(
            DailyWeather(
                date=day,
                t_mean=t_mean,
                wind_mean=_parse_value("FG", row.get("FG", "")),
                radiation=_parse_value("Q", row.get("Q", "")),
                t_min=_parse_value("TN", row.get("TN", "")),
                t_max=_parse_value("TX", row.get("TX", "")),
                provisional=False,
                source=f"knmi:{row.get('STN', '').strip()}",
            )
        )
    result.sort(key=lambda w: w.date)
    if result and provisional_days > 0:
        end = requested_end or result[-1].date
        threshold = end - timedelta(days=provisional_days - 1)
        result = [replace(w, provisional=w.date >= threshold) for w in result]
    return result


class KnmiClient:
    """Async client for one KNMI station; the aiohttp session is injected (ADR 0002)."""

    def __init__(
        self,
        station: int | str,
        provisional_days: int = 1,
        variables: Sequence[str] = DEFAULT_VARS,
        url: str = KNMI_DAILY_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.station = int(station)
        self.provisional_days = provisional_days
        self.variables = tuple(variables)
        self.url = url
        self.timeout_s = timeout_s

    async def fetch_daily(self, start: date, end: date, session: Any) -> list[DailyWeather]:
        """Fetch ``start``..``end`` in chunks of at most one year each."""
        return await fetch_daily(
            start,
            end,
            session,
            station=self.station,
            provisional_days=self.provisional_days,
            variables=self.variables,
            url=self.url,
            timeout_s=self.timeout_s,
        )


async def fetch_daily(
    start: date,
    end: date,
    session: Any,
    station: int | str = 260,
    provisional_days: int = 1,
    variables: Sequence[str] = DEFAULT_VARS,
    url: str = KNMI_DAILY_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[DailyWeather]:
    """POST the form to the KNMI API with an injected ``aiohttp.ClientSession``.

    aiohttp is imported lazily so that the core works without it installed.
    """
    try:
        import aiohttp  # optional dependency, imported lazily

        timeout: Any = aiohttp.ClientTimeout(total=timeout_s)
    except ImportError:  # pragma: no cover - exercised only without aiohttp
        timeout = None
    result: list[DailyWeather] = []
    for chunk_start, chunk_end in chunk_date_range(start, end):
        body = encode_form_body(build_form_body(chunk_start, chunk_end, station, variables))
        kwargs: dict[str, Any] = {
            "data": body,
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        async with session.post(url, **kwargs) as response:
            response.raise_for_status()
            text = await response.text()
        result.extend(
            parse_knmi_daggegevens(text, requested_end=end, provisional_days=provisional_days)
        )
    _LOGGER.debug("KNMI station %s: %d days fetched for %s..%s", station, len(result), start, end)
    return result


class KnmiProvider:
    """:class:`WeatherProvider` implementation with a bound session (ARCHITECTURE section 10).

    ``session`` is an ``aiohttp.ClientSession`` (in Home Assistant the shared session).
    """

    def __init__(
        self, session: Any, station_id: int | str, provisional_days: int = 1, **kwargs: Any
    ) -> None:
        self.session = session
        self.client = KnmiClient(station_id, provisional_days=provisional_days, **kwargs)

    async def fetch_daily(self, start: date, end: date) -> list[DailyWeather]:
        """Fetch ``start``..``end`` for the configured station."""
        return await self.client.fetch_daily(start, end, self.session)
