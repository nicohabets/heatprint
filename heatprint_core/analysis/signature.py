"""Energy-signature fit, PRISM style (METHODS section 7).

Model per period (usually a heating season)::

    Q_space(d) = a + b * H(d) + c * wind_mean(d)     with  H(d) = max(0, T_b - TAC(d))

``T_b`` is found by grid search (default 6.0..22.0 in steps of 0.1); for each candidate
an OLS fit gives ``a``, ``b`` (and ``c`` when ``fit_wind``), the candidate with the
lowest SSE wins. Outliers (``|residual| > outlier_k * rmse``) are marked once and the
fit is repeated without them. Confidence intervals: ``b +- t(n-p) * SE(b)`` and the
profile interval of ``T_b`` (all grid points with
``SSE <= SSE_min * (1 + F_0.95(1, n-p) / (n-p))``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from ..constants import W_PER_K_FROM_KWH_PER_K_DAY
from ..flags import is_usable
from ..models import DailyRecord, Period, SignatureFit
from .ols import OlsResult, f_quantile_95_1, ols, t_quantile_975

_LOGGER = logging.getLogger(__name__)

TAC_KEYS: dict[str, str] = {"tac_house": "house", "tac_pbl": "pbl"}


@dataclass(frozen=True)
class FitDay:
    """One usable day of the fit."""

    date: date
    tac: float
    wind: float | None
    heat: float


@dataclass(frozen=True)
class GridPoint:
    """SSE of one balance-temperature candidate."""

    balance_temp: float
    sse: float


@dataclass(frozen=True)
class GridFit:
    """Best grid point with its OLS result and the SSE profile."""

    balance_temp: float
    result: OlsResult
    heating: list[float]
    profile: list[GridPoint]
    fit_wind: bool


def tac_key_for_preset(preset_name: str) -> str:
    """``"house"`` -> ``"tac_house"``, ``"pbl"`` -> ``"tac_pbl"``."""
    for key, name in TAC_KEYS.items():
        if name == preset_name:
            return key
    raise ValueError(f"unknown TAC preset: {preset_name!r}")


def select_days(
    records: Iterable[DailyRecord],
    period: Period,
    tac_key: str = "tac_house",
    exclude_dates: Iterable[date] = (),
) -> list[FitDay]:
    """Days in ``period`` without exclusion flags and with a TAC value (METHODS 7 step 1)."""
    excluded = set(exclude_dates)
    days: list[FitDay] = []
    for record in records:
        if not period.contains(record.date) or record.date in excluded:
            continue
        if not is_usable(record.flags):
            continue
        tac = getattr(record, tac_key, None)
        if tac is None or record.heat_space_kwh is None:
            continue
        days.append(FitDay(record.date, float(tac), record.wind_mean, float(record.heat_space_kwh)))
    return days


def grid_search(
    days: Sequence[FitDay],
    fit_wind: bool,
    tb_range: tuple[float, float] = (6.0, 22.0),
    step: float = 0.1,
    min_heating_days: int = 15,
) -> GridFit | None:
    """Grid search over the balance temperature (METHODS section 7 step 2)."""
    heat = [d.heat for d in days]
    wind = [d.wind or 0.0 for d in days] if fit_wind else None
    tacs = [d.tac for d in days]
    n_steps = int(round((tb_range[1] - tb_range[0]) / step))
    best_tb: float | None = None
    best_result: OlsResult | None = None
    best_heating: list[float] = []
    profile: list[GridPoint] = []
    for i in range(n_steps + 1):
        tb = round(tb_range[0] + i * step, 6)
        heating = [max(0.0, tb - tac) for tac in tacs]
        if sum(1 for h in heating if h > 0) < min_heating_days:
            continue
        xs: list[Sequence[float]] = [heating]
        if wind is not None:
            xs.append(wind)
        result = ols(heat, xs)
        if result is None:
            continue
        profile.append(GridPoint(tb, result.sse))
        if best_result is None or result.sse < best_result.sse:
            best_tb, best_result, best_heating = tb, result, heating
    if best_result is None or best_tb is None:
        return None
    return GridFit(best_tb, best_result, best_heating, profile, fit_wind)


def _residuals(days: Sequence[FitDay], fit: GridFit) -> list[float]:
    coefficients = fit.result.coefficients
    residuals = []
    for day, heating in zip(days, fit.heating, strict=True):
        prediction = coefficients[0] + coefficients[1] * heating
        if fit.fit_wind:
            prediction += coefficients[2] * (day.wind or 0.0)
        residuals.append(day.heat - prediction)
    return residuals


def _balance_ci(fit: GridFit) -> tuple[float, float]:
    result = fit.result
    df = result.df
    if df <= 0:
        return fit.balance_temp, fit.balance_temp
    threshold = result.sse * (1 + f_quantile_95_1(df) / df)
    inside = [point.balance_temp for point in fit.profile if point.sse <= threshold]
    if not inside:
        return fit.balance_temp, fit.balance_temp
    return min(inside), max(inside)


def _to_signature(
    fit: GridFit,
    period: Period,
    tac_key: str,
    site_id: str,
    outliers: list[date],
    fitted_at: datetime,
) -> SignatureFit:
    result = fit.result
    slope = result.coefficients[1]
    df = result.df
    t_value = t_quantile_975(df) if df > 0 else float("inf")
    se_slope = result.standard_errors[1]
    ci_slope = (slope - t_value * se_slope, slope + t_value * se_slope)
    if any(math.isnan(v) or math.isinf(v) for v in ci_slope):
        ci_slope = (slope, slope)
    return SignatureFit(
        site_id=site_id,
        period=period,
        tac_preset=TAC_KEYS.get(tac_key, tac_key),
        balance_temp=fit.balance_temp,
        intercept_a=result.coefficients[0],
        slope_b=slope,
        wind_c=result.coefficients[2] if fit.fit_wind else None,
        ua_w_per_k=slope * W_PER_K_FROM_KWH_PER_K_DAY,
        r2=result.r2,
        rmse=result.rmse,
        n_days=result.n,
        n_heating_days=sum(1 for h in fit.heating if h > 0),
        ci95_slope=ci_slope,
        ci95_balance=_balance_ci(fit),
        fitted_at=fitted_at,
        sse=result.sse,
        outliers=sorted(outliers),
    )


def fit_signature(
    records: Iterable[DailyRecord],
    period: Period,
    tac_key: str = "tac_house",
    fit_wind: bool = True,
    tb_range: tuple[float, float] = (6.0, 22.0),
    step: float = 0.1,
    min_days: int = 30,
    min_heating_days: int = 15,
    outlier_k: float | None = 4.0,
    *,
    site_id: str | None = None,
    fitted_at: datetime | None = None,
    exclude_dates: Iterable[date] = (),
) -> SignatureFit | None:
    """Fit the energy signature over ``period`` (METHODS section 7).

    Returns None when fewer than ``min_days`` usable days exist or no balance
    temperature yields at least ``min_heating_days`` heating days. With ``fit_wind``
    days without wind data are dropped; if that leaves too few days the wind term is
    dropped instead. ``outlier_k=None`` skips the outlier pass (used by the bootstrap).
    """
    records = list(records)
    if site_id is None:
        site_id = records[0].site_id if records else ""
    days = select_days(records, period, tac_key, exclude_dates)
    if fit_wind:
        with_wind = [d for d in days if d.wind is not None]
        if len(with_wind) >= min_days:
            days = with_wind
        else:
            _LOGGER.debug("not enough days with wind data, fitting without wind term")
            fit_wind = False
    if len(days) < min_days:
        _LOGGER.debug("signature fit: only %d usable days (< %d)", len(days), min_days)
        return None

    fit = grid_search(days, fit_wind, tb_range, step, min_heating_days)
    if fit is None:
        _LOGGER.debug("signature fit: no balance temperature with enough heating days")
        return None

    outliers: list[date] = []
    if outlier_k is not None and fit.result.rmse > 0:
        residuals = _residuals(days, fit)
        threshold = outlier_k * fit.result.rmse
        outliers = [d.date for d, r in zip(days, residuals, strict=True) if abs(r) > threshold]
        if outliers:
            outlier_dates = set(outliers)
            kept = [d for d in days if d.date not in outlier_dates]
            refit = (
                grid_search(kept, fit_wind, tb_range, step, min_heating_days)
                if len(kept) >= min_days
                else None
            )
            if refit is not None:
                _LOGGER.debug("signature fit: %d outlier(s) removed, refitted", len(outliers))
                days, fit = kept, refit
            else:
                outliers = []

    stamp = fitted_at or datetime.now(tz=UTC)
    return _to_signature(fit, period, tac_key, site_id, outliers, stamp)


def residuals_by_date(fit: SignatureFit, records: Iterable[DailyRecord]) -> dict[date, float]:
    """Residual ``Q_space - prediction`` per usable day of ``fit.period`` (for the UI)."""
    tac_key = tac_key_for_preset(fit.tac_preset)
    result: dict[date, float] = {}
    for day in select_days(records, fit.period, tac_key):
        result[day.date] = day.heat - fit.predict(day.tac, day.wind)
    return result
