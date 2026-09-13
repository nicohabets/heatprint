"""Heating seasons and gas years.

A season starts on ``SeasonConfig.start_month`` / ``start_day`` (default 1 October,
the Dutch gas year) and ends the day before the next start. Labels are ``"2025/26"``
for seasons that span two calendar years and ``"2026"`` for calendar-year seasons
(1 January start, mindergas style).
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta

from .models import Season, SeasonConfig

_LABEL_RE = re.compile(r"^(\d{4})(?:/(\d{2}))?$")


def _safe_date(year: int, month: int, day: int) -> date:
    """Build a date, clamping the day for short months (e.g. 30 Feb -> 28/29 Feb)."""
    return date(year, month, min(day, monthrange(year, month)[1]))


def season_start(year: int, cfg: SeasonConfig) -> date:
    """First day of the season that starts in ``year``."""
    return _safe_date(year, cfg.start_month, cfg.start_day)


def season_label(start_year: int, cfg: SeasonConfig) -> str:
    """Label of the season starting in ``start_year``: ``"2025/26"`` or ``"2026"``."""
    if cfg.start_month == 1 and cfg.start_day == 1:
        return str(start_year)
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def season_for(day: date, cfg: SeasonConfig | None = None) -> Season:
    """Return the season that contains ``day``."""
    cfg = cfg or SeasonConfig()
    start_year = day.year if day >= season_start(day.year, cfg) else day.year - 1
    start = season_start(start_year, cfg)
    end = season_start(start_year + 1, cfg) - timedelta(days=1)
    return Season(label=season_label(start_year, cfg), start=start, end=end)


def season_window(label: str, cfg: SeasonConfig | None = None) -> Season:
    """Return the season for a label such as ``"2025/26"`` or ``"2026"``."""
    cfg = cfg or SeasonConfig()
    match = _LABEL_RE.match(label.strip())
    if not match:
        raise ValueError(f"invalid season label: {label!r}")
    start_year = int(match.group(1))
    start = season_start(start_year, cfg)
    end = season_start(start_year + 1, cfg) - timedelta(days=1)
    return Season(label=season_label(start_year, cfg), start=start, end=end)


def previous_season(season: Season, cfg: SeasonConfig | None = None) -> Season:
    """Return the season immediately before ``season``."""
    return season_for(season.start - timedelta(days=1), cfg)


def next_season(season: Season, cfg: SeasonConfig | None = None) -> Season:
    """Return the season immediately after ``season``."""
    return season_for(season.end + timedelta(days=1), cfg)


def seasons_between(start: date, end: date, cfg: SeasonConfig | None = None) -> list[Season]:
    """All seasons that overlap the inclusive date range ``start``..``end``."""
    result: list[Season] = []
    current = season_for(start, cfg)
    while current.start <= end:
        result.append(current)
        current = next_season(current, cfg)
    return result
