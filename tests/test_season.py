"""Season labels and windows."""

from __future__ import annotations

from datetime import date

import pytest

from heatprint_core.models import SeasonConfig
from heatprint_core.season import (
    next_season,
    previous_season,
    season_for,
    season_window,
    seasons_between,
)


def test_gas_year_labels() -> None:
    cfg = SeasonConfig(start_month=10, start_day=1)
    season = season_for(date(2026, 1, 15), cfg)
    assert season.label == "2025/26"
    assert season.start == date(2025, 10, 1)
    assert season.end == date(2026, 9, 30)
    assert season_for(date(2025, 10, 1), cfg).label == "2025/26"
    assert season_for(date(2025, 9, 30), cfg).label == "2024/25"
    assert season_for(date(1999, 12, 1), cfg).label == "1999/00"


def test_calendar_year_labels() -> None:
    cfg = SeasonConfig(start_month=1, start_day=1)
    season = season_for(date(2026, 7, 1), cfg)
    assert season.label == "2026"
    assert (season.start, season.end) == (date(2026, 1, 1), date(2026, 12, 31))


def test_season_window_from_label() -> None:
    season = season_window("2025/26")
    assert season.start == date(2025, 10, 1) and season.end == date(2026, 9, 30)
    calendar = season_window("2026", SeasonConfig(1, 1))
    assert calendar.start == date(2026, 1, 1)
    july = season_window("2025/26", SeasonConfig(7, 1))
    assert july.start == date(2025, 7, 1) and july.end == date(2026, 6, 30)
    with pytest.raises(ValueError):
        season_window("winter")


def test_neighbouring_seasons() -> None:
    season = season_window("2025/26")
    assert previous_season(season).label == "2024/25"
    assert next_season(season).label == "2026/27"
    labels = [s.label for s in seasons_between(date(2024, 11, 1), date(2026, 2, 1))]
    assert labels == ["2024/25", "2025/26"]
