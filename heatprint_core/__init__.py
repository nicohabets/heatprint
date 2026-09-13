"""Heatprint core: weather-corrected heating analytics, pure Python (see docs/METHODS.md).

The package has no runtime dependencies (ADR 0002) and no Home Assistant imports
(ADR 0001). The main entry points are re-exported here.
"""

from __future__ import annotations

from .analysis import (
    InsufficientDataError,
    compare_periods,
    fit_signature,
    forecast_season,
    measure_effect,
    normalized_consumption,
    saving_between,
)
from .dhw import estimate_baseline, split_dhw
from .flags import Flag
from .heat import carrier_to_heat, cop_day
from .importers import parse_readings_csv
from .methods import compute_all, compute_day, preset, t_eff, tac_series
from .models import (
    CarrierInput,
    CarrierUnit,
    ClassicParams,
    Climatology,
    Comparison,
    Conversion,
    ConversionMode,
    DailyEnergy,
    DailyRecord,
    DailyWeather,
    DhwConfig,
    DhwMode,
    Forecast,
    Generator,
    GeneratorKind,
    HouseParams,
    Measure,
    MeasureCategory,
    MethodConfig,
    PblParams,
    Period,
    Provider,
    Role,
    Season,
    SeasonConfig,
    SignatureFit,
    Site,
    WeatherSourceConfig,
)
from .pipeline import build_daily_records, estimate_baselines
from .readings import readings_to_daily
from .season import season_for, season_window
from .weather import (
    KnmiClient,
    OpenMeteoClient,
    WeatherProvider,
    build_climatology,
    merge_weather,
    parse_knmi_daggegevens,
    parse_open_meteo_hourly,
    remaining_season_dd,
)

__version__ = "0.1.0"

__all__ = [
    "CarrierInput",
    "CarrierUnit",
    "ClassicParams",
    "Climatology",
    "Comparison",
    "Conversion",
    "ConversionMode",
    "DailyEnergy",
    "DailyRecord",
    "DailyWeather",
    "DhwConfig",
    "DhwMode",
    "Flag",
    "Forecast",
    "Generator",
    "GeneratorKind",
    "HouseParams",
    "InsufficientDataError",
    "KnmiClient",
    "Measure",
    "MeasureCategory",
    "MethodConfig",
    "OpenMeteoClient",
    "PblParams",
    "Period",
    "Provider",
    "Role",
    "Season",
    "SeasonConfig",
    "SignatureFit",
    "Site",
    "WeatherProvider",
    "WeatherSourceConfig",
    "__version__",
    "build_climatology",
    "build_daily_records",
    "carrier_to_heat",
    "compare_periods",
    "compute_all",
    "compute_day",
    "cop_day",
    "estimate_baseline",
    "estimate_baselines",
    "fit_signature",
    "forecast_season",
    "measure_effect",
    "merge_weather",
    "normalized_consumption",
    "parse_knmi_daggegevens",
    "parse_open_meteo_hourly",
    "parse_readings_csv",
    "preset",
    "readings_to_daily",
    "remaining_season_dd",
    "saving_between",
    "season_for",
    "season_window",
    "split_dhw",
    "t_eff",
    "tac_series",
]
