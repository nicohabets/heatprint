"""Weather merge rules (METHODS section 2)."""

from __future__ import annotations

from datetime import date

from heatprint_core.models import DailyWeather
from heatprint_core.weather.base import WeatherProvider, merge_weather, weather_by_date


def test_merge_new_overrides_provisional_only() -> None:
    day = date(2026, 1, 10)
    definitive = DailyWeather(day, 3.0, provisional=False, source="knmi:380")
    provisional = DailyWeather(day, 3.5, provisional=True, source="open_meteo")
    newer = DailyWeather(day, 3.2, provisional=False, source="knmi:380")
    # A provisional value does not replace a definitive one.
    assert merge_weather([definitive], [provisional])[day] is definitive
    # A definitive value replaces a provisional one, and a definitive one.
    assert merge_weather([provisional], [definitive])[day] is definitive
    assert merge_weather([definitive], [newer])[day] is newer
    # A provisional value replaces a provisional one.
    assert (
        merge_weather([provisional], [DailyWeather(day, 4.0, provisional=True)])[day].t_mean == 4.0
    )


def test_merge_accepts_mappings_and_sorts() -> None:
    first = DailyWeather(date(2026, 1, 2), 1.0)
    second = DailyWeather(date(2026, 1, 1), 2.0)
    merged = merge_weather({first.date: first}, [second])
    assert list(merged) == [date(2026, 1, 1), date(2026, 1, 2)]
    assert weather_by_date([first, second]) == merged


def test_provider_protocol() -> None:
    class Dummy:
        async def fetch_daily(self, start: date, end: date) -> list[DailyWeather]:
            return []

    assert isinstance(Dummy(), WeatherProvider)
