"""Weather providers and climatology (METHODS sections 2 and 8.1)."""

from .base import WeatherProvider, merge_weather, weather_by_date
from .climatology import build_climatology, leap_doy, remaining_season_dd, season_dd_clim
from .knmi import KnmiClient, KnmiProvider, chunk_date_range, parse_knmi_daggegevens
from .open_meteo import (
    OpenMeteoClient,
    OpenMeteoProvider,
    parse_open_meteo_daily,
    parse_open_meteo_hourly,
)

__all__ = [
    "KnmiClient",
    "KnmiProvider",
    "OpenMeteoClient",
    "OpenMeteoProvider",
    "WeatherProvider",
    "build_climatology",
    "chunk_date_range",
    "leap_doy",
    "merge_weather",
    "parse_knmi_daggegevens",
    "parse_open_meteo_daily",
    "parse_open_meteo_hourly",
    "remaining_season_dd",
    "season_dd_clim",
    "weather_by_date",
]
