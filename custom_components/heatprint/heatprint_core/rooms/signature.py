"""Per-room energy-signature fit, reusing the site TAC / PRISM machinery (METHODS §12.4).

Model::

    heat_room_kwh_r(d) = a_r + b_r * max(0, T_b,r - TAC(d))

Room fits always use the site TAC (house preset). ``wind_c`` is not stored.
Days with ``ROOM_DEMAND_MISSING`` are excluded. ``n >= 30`` and at least 15
heating days, same as the site fit.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime

from ..analysis.ols import t_quantile_975
from ..analysis.signature import FitDay, GridFit, grid_search
from ..constants import W_PER_K_FROM_KWH_PER_K_DAY
from ..flags import Flag, is_room_usable, is_usable
from ..models import DailyRecord, DailyRoomRecord, Period, Room, RoomSignatureFit
from .allocation import indicative_ua_w_per_k, room_records_by_id

_LOGGER = logging.getLogger(__name__)


def select_room_days(
    room_records: Iterable[DailyRoomRecord],
    site_records: Iterable[DailyRecord],
    period: Period,
    tac_key: str = "tac_house",
    exclude_dates: Iterable[date] = (),
) -> list[FitDay]:
    """Usable room-days with a site TAC, matching METHODS 12.4 / 7 step 1."""
    site_by_date = {record.date: record for record in site_records}
    excluded = set(exclude_dates)
    days: list[FitDay] = []
    for record in room_records:
        if not period.contains(record.date) or record.date in excluded:
            continue
        if not is_room_usable(record.flags) or record.heat_room_kwh is None:
            continue
        site = site_by_date.get(record.date)
        if site is None or not is_usable(site.flags):
            continue
        tac = getattr(site, tac_key, None)
        if tac is None:
            continue
        days.append(FitDay(record.date, float(tac), site.wind_mean, float(record.heat_room_kwh)))
    return days


def _residuals(days: Sequence[FitDay], fit: GridFit) -> list[float]:
    intercept, slope = fit.result.coefficients[0], fit.result.coefficients[1]
    return [
        day.heat - (intercept + slope * heating)
        for day, heating in zip(days, fit.heating, strict=True)
    ]


def _balance_ci(fit: GridFit) -> tuple[float, float]:
    result = fit.result
    if result.df <= 0:
        return fit.balance_temp, fit.balance_temp
    from ..analysis.ols import f_quantile_95_1

    threshold = result.sse * (1 + f_quantile_95_1(result.df) / result.df)
    inside = [point.balance_temp for point in fit.profile if point.sse <= threshold]
    if not inside:
        return fit.balance_temp, fit.balance_temp
    return min(inside), max(inside)


def _indicative_from_records(
    room_records: Iterable[DailyRoomRecord],
    site_records: Iterable[DailyRecord],
    period: Period,
) -> float | None:
    """Median indicative UA over qualifying heating days (immediate estimate)."""
    site_by_date = {record.date: record for record in site_records}
    estimates: list[float] = []
    for record in room_records:
        if not period.contains(record.date) or not is_room_usable(record.flags):
            continue
        site = site_by_date.get(record.date)
        hours = None
        if record.demand_integral is not None:
            hours = float(record.demand_integral) * 24.0
        value = indicative_ua_w_per_k(
            record.heat_room_kwh,
            record.t_room_mean,
            site.t_mean if site is not None else None,
            hours,
        )
        if value is not None and math.isfinite(value) and 0 < value < 5000:
            estimates.append(value)
    if not estimates:
        return None
    estimates.sort()
    mid = len(estimates) // 2
    if len(estimates) % 2:
        return estimates[mid]
    return (estimates[mid - 1] + estimates[mid]) / 2.0


def apply_room_not_fitted(
    room_records: Iterable[DailyRoomRecord],
    site_records: Iterable[DailyRecord],
    *,
    min_days: int = 30,
    skip_room_ids: Iterable[str] = (),
    tac_key: str = "tac_house",
) -> set[str]:
    """Add ``ROOM_NOT_FITTED`` on rooms with fewer than ``min_days`` usable fit days.

    Rooms in ``skip_room_ids`` (already fitted) are left unchanged. Returns the
    room ids that were flagged. Mutates ``record.flags`` in place.
    """
    records = list(room_records)
    if not records:
        return set()
    skip = set(skip_room_ids)
    period = Period(min(record.date for record in records), max(record.date for record in records))
    flagged: set[str] = set()
    for room_id, rows in room_records_by_id(records).items():
        if room_id in skip:
            continue
        days = select_room_days(rows, site_records, period, tac_key)
        if len(days) < min_days:
            flagged.add(room_id)
            for row in rows:
                row.flags.add(Flag.ROOM_NOT_FITTED)
    return flagged


def fit_room_signature(
    room: Room,
    room_records: Iterable[DailyRoomRecord],
    site_records: Iterable[DailyRecord],
    period: Period,
    *,
    tac_key: str = "tac_house",
    tb_range: tuple[float, float] = (6.0, 22.0),
    step: float = 0.1,
    min_days: int = 30,
    min_heating_days: int = 15,
    outlier_k: float | None = 4.0,
    fitted_at: datetime | None = None,
    exclude_dates: Iterable[date] = (),
) -> RoomSignatureFit | None:
    """Fit the apparent room energy signature (METHODS section 12.4).

    Returns None when fewer than ``min_days`` usable days exist. The caller
    should then surface ``ROOM_NOT_FITTED`` and the indicative UA instead.
    """
    room_records = list(room_records)
    site_records = list(site_records)
    days = select_room_days(room_records, site_records, period, tac_key, exclude_dates)
    indicative = _indicative_from_records(room_records, site_records, period)
    if len(days) < min_days:
        _LOGGER.debug("room %s fit: only %d usable days (< %d)", room.id, len(days), min_days)
        apply_room_not_fitted(
            room_records,
            site_records,
            min_days=min_days,
            tac_key=tac_key,
        )
        return None

    fit = grid_search(
        days, fit_wind=False, tb_range=tb_range, step=step, min_heating_days=min_heating_days
    )
    if fit is None:
        _LOGGER.debug("room %s fit: no balance temperature with enough heating days", room.id)
        return None

    outliers: list[date] = []
    if outlier_k is not None and fit.result.rmse > 0:
        residuals = _residuals(days, fit)
        threshold = outlier_k * fit.result.rmse
        outliers = [
            d.date for d, residual in zip(days, residuals, strict=True) if abs(residual) > threshold
        ]
        if outliers:
            kept = [day for day in days if day.date not in set(outliers)]
            refit = (
                grid_search(kept, False, tb_range, step, min_heating_days)
                if len(kept) >= min_days
                else None
            )
            if refit is not None:
                days, fit = kept, refit
            else:
                outliers = []

    result = fit.result
    slope = result.coefficients[1]
    df = result.df
    t_value = t_quantile_975(df) if df > 0 else float("inf")
    se_slope = result.standard_errors[1]
    ci_slope = (slope - t_value * se_slope, slope + t_value * se_slope)
    if any(math.isnan(value) or math.isinf(value) for value in ci_slope):
        ci_slope = (slope, slope)
    ua = slope * W_PER_K_FROM_KWH_PER_K_DAY
    per_m2 = ua / room.floor_area_m2 if room.floor_area_m2 and room.floor_area_m2 > 0 else None
    stamp = fitted_at or datetime.now(tz=UTC)
    return RoomSignatureFit(
        room_id=room.id,
        period=period,
        balance_temp=fit.balance_temp,
        intercept_a=result.coefficients[0],
        slope_b=slope,
        ua_w_per_k=ua,
        r2=result.r2,
        rmse=result.rmse,
        n_days=result.n,
        n_heating_days=sum(1 for heating in fit.heating if heating > 0),
        ci95_slope=ci_slope,
        ci95_balance=_balance_ci(fit),
        fitted_at=stamp,
        sse=result.sse,
        outliers=sorted(outliers),
        ua_w_per_k_per_m2=per_m2,
        ua_indicative_w_per_k=indicative,
    )
