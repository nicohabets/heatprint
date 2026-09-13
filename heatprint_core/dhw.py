"""Domestic hot water (DHW) and cooking split (METHODS section 6).

Per generator with ``role = both`` the total heat is split into ``Q_dhw`` and
``Q_space``:

- ``measured``: ``Q_dhw`` from a separate sensor, ``Q_space = max(0, Q_total - Q_dhw)``.
- ``baseline`` (default): ``B`` = mean daily consumption over the summer window of the
  last complete summer (at least ``min_days`` days); ``Q_dhw = min(Q_total, B * conv)``.
  Without a complete summer: the lowest rolling 30-day mean of the series.
- ``fixed``: a fixed amount per day in carrier units.
- ``none``: everything is space heating.

``role = dhw``: ``Q_space = 0``; ``role = space``: ``Q_dhw = 0``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, timedelta

from .heat import static_heat_per_unit
from .models import DhwMode, Generator, Role

_LOGGER = logging.getLogger(__name__)

ROLLING_DAYS = 30


MonthDay = str | tuple[int, int]


def parse_mmdd(value: MonthDay) -> tuple[int, int]:
    """Parse ``"MM-DD"`` (or pass through a ``(month, day)`` tuple) into ``(month, day)``."""
    if isinstance(value, tuple):
        month, day = value
        return int(month), int(day)
    month_text, day_text = value.strip().split("-")
    return int(month_text), int(day_text)


def summer_window(
    year: int, summer_start_mmdd: MonthDay, summer_end_mmdd: MonthDay
) -> tuple[date, date]:
    """Inclusive summer window for ``year``; the end wraps into the next year if needed."""
    start_month, start_day = parse_mmdd(summer_start_mmdd)
    end_month, end_day = parse_mmdd(summer_end_mmdd)
    start = date(year, start_month, start_day)
    end = date(year, end_month, end_day)
    if end < start:
        end = date(year + 1, end_month, end_day)
    return start, end


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def lowest_rolling_mean(
    daily_amounts: Mapping[date, float], window_days: int = ROLLING_DAYS, min_days: int = 30
) -> float | None:
    """Lowest mean over any ``window_days`` calendar-day window holding >= ``min_days`` values."""
    days = sorted(daily_amounts)
    if not days:
        return None
    best: float | None = None
    end_index = 0
    for start_index, start_day in enumerate(days):
        window_end = start_day + timedelta(days=window_days - 1)
        while end_index < len(days) and days[end_index] <= window_end:
            end_index += 1
        window = days[start_index:end_index]
        if len(window) < min_days:
            continue
        mean = _mean([daily_amounts[d] for d in window])
        if best is None or mean < best:
            best = mean
    return best


def estimate_baseline(
    daily_amounts: Mapping[date, float],
    summer_start_mmdd: MonthDay = "06-01",
    summer_end_mmdd: MonthDay = "08-31",
    min_days: int = 30,
) -> float | None:
    """Mean daily amount over the last complete summer window (METHODS section 6).

    The unit of the result is the unit of ``daily_amounts`` (carrier units or kWh).
    Falls back to the lowest rolling 30-day mean when no complete summer with at least
    ``min_days`` data days exists; None when the series is too short for that as well.
    """
    if not daily_amounts:
        return None
    last_day = max(daily_amounts)
    first_day = min(daily_amounts)
    for year in range(last_day.year, first_day.year - 2, -1):
        start, end = summer_window(year, summer_start_mmdd, summer_end_mmdd)
        if end > last_day:
            continue  # summer not complete yet
        values = [amount for day, amount in daily_amounts.items() if start <= day <= end]
        if len(values) >= min_days:
            return _mean(values)
    fallback = lowest_rolling_mean(daily_amounts, ROLLING_DAYS, min_days)
    if fallback is None:
        _LOGGER.debug("no summer window and fewer than %d days: no DHW baseline", min_days)
    return fallback


def split_dhw(
    generator: Generator,
    heat_total_kwh: float,
    carrier_amount: float | None,
    baseline: float | None,
    measured_dhw_kwh: float | None = None,
    baseline_in_kwh: bool = False,
) -> tuple[float, float]:
    """Split total heat into ``(heat_dhw_kwh, heat_space_kwh)`` (METHODS section 6).

    ``baseline`` is the daily DHW baseline in carrier units (converted with today's
    actual conversion ``Q_total / carrier_amount`` or, when the carrier amount is
    unknown or zero, the static conversion of the generator). Pass
    ``baseline_in_kwh=True`` when the baseline was estimated on a heat series (kWh).
    """
    heat_total_kwh = max(0.0, heat_total_kwh)
    if generator.role is Role.DHW:
        return heat_total_kwh, 0.0
    if generator.role is Role.SPACE:
        return 0.0, heat_total_kwh

    mode = generator.dhw.mode
    if mode is DhwMode.NONE:
        return 0.0, heat_total_kwh

    if mode is DhwMode.MEASURED and measured_dhw_kwh is not None:
        dhw = max(0.0, measured_dhw_kwh)
        return dhw, max(0.0, heat_total_kwh - dhw)

    if mode is DhwMode.FIXED:
        fixed = generator.dhw.fixed_per_day
        if fixed is None:
            return 0.0, heat_total_kwh
        dhw = min(heat_total_kwh, _to_kwh(generator, fixed, heat_total_kwh, carrier_amount, False))
        return dhw, heat_total_kwh - dhw

    # baseline (default), also the fallback of ``measured`` without a measurement
    if baseline is None:
        return 0.0, heat_total_kwh
    dhw = min(
        heat_total_kwh,
        _to_kwh(generator, baseline, heat_total_kwh, carrier_amount, baseline_in_kwh),
    )
    return dhw, heat_total_kwh - dhw


def _to_kwh(
    generator: Generator,
    amount: float,
    heat_total_kwh: float,
    carrier_amount: float | None,
    in_kwh: bool,
) -> float:
    """Convert a DHW amount to kWh with today's actual conversion, else the static one."""
    if in_kwh:
        return max(0.0, amount)
    if carrier_amount is not None and carrier_amount > 0 and heat_total_kwh > 0:
        return max(0.0, amount) * heat_total_kwh / carrier_amount
    return max(0.0, amount) * static_heat_per_unit(generator)
