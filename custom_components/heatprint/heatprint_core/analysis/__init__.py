"""Analyses on daily records: signature fit, normalisation, comparison, forecast (METHODS 7-8)."""

from .compare import InsufficientDataError, compare_periods, measure_effect, period_stats
from .forecast import forecast_carrier_amounts, forecast_season, generator_shares_last_days
from .normalize import normalized_consumption, saving_between
from .ols import OlsResult, f_quantile_95_1, ols, percentile, t_quantile_975
from .signature import fit_signature, residuals_by_date

__all__ = [
    "InsufficientDataError",
    "OlsResult",
    "compare_periods",
    "f_quantile_95_1",
    "fit_signature",
    "forecast_carrier_amounts",
    "forecast_season",
    "generator_shares_last_days",
    "measure_effect",
    "normalized_consumption",
    "ols",
    "percentile",
    "period_stats",
    "residuals_by_date",
    "saving_between",
    "t_quantile_975",
]
