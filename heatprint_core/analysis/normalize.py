"""Normalised annual/seasonal consumption (NAC) and savings (METHODS sections 8.1-8.2).

::

    NAC = sum over days of the season window of
          a + b * max(0, T_b - TAC_clim(doy)) + c * wind_clim(doy)

Saving between fit 1 (before) and fit 2 (after): ``S = (NAC_1 - NAC_2) / NAC_1``.
The 95% interval comes from a bootstrap: resample the days of both periods with
replacement, refit (coarser grid, no outlier pass) and take the 2.5% and 97.5%
percentiles of ``S``.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Iterable
from datetime import date, timedelta

from ..models import Climatology, DailyRecord, Period, Season, SignatureFit
from ..weather.climatology import climatology_value
from .ols import percentile
from .signature import fit_signature, select_days, tac_key_for_preset

_LOGGER = logging.getLogger(__name__)

Window = Season | Period | tuple[date, date]


def _window_dates(window: Window) -> tuple[date, date]:
    if isinstance(window, tuple):
        return window
    return window.start, window.end


def normalized_consumption(
    fit: SignatureFit, climatology: Climatology, season_window: Window
) -> float:
    """NAC of ``fit`` over the days of ``season_window`` on the climatology (METHODS 8.2).

    The window only defines which days of year are summed; its years are irrelevant.
    Days of year without climatology are skipped.
    """
    start, end = _window_dates(season_window)
    total = 0.0
    day = start
    while day <= end:
        tac = climatology_value(climatology, "tac", day)
        if tac is not None:
            wind = climatology_value(climatology, "wind", day) if fit.wind_c is not None else None
            total += fit.predict(tac, wind)
        day += timedelta(days=1)
    return total


def saving_pct(nac_before: float, nac_after: float) -> float:
    """Saving in percent: ``(NAC_1 - NAC_2) / NAC_1 * 100``."""
    if nac_before == 0:
        return 0.0
    return (nac_before - nac_after) / nac_before * 100.0


def _bootstrap_fit(
    rng: random.Random,
    records: list[DailyRecord],
    fit: SignatureFit,
    step: float,
) -> SignatureFit | None:
    if not records:
        return None
    sample = [rng.choice(records) for _ in range(len(records))]
    return fit_signature(
        sample,
        fit.period,
        tac_key=tac_key_for_preset(fit.tac_preset),
        fit_wind=fit.wind_c is not None,
        step=step,
        outlier_k=None,
        site_id=fit.site_id,
        fitted_at=fit.fitted_at,
    )


def fit_records(records: Iterable[DailyRecord], fit: SignatureFit) -> list[DailyRecord]:
    """The records that ``fit`` was based on (usable days in its period minus outliers)."""
    records = list(records)
    tac_key = tac_key_for_preset(fit.tac_preset)
    dates = {d.date for d in select_days(records, fit.period, tac_key, fit.outliers)}
    return [r for r in records if r.date in dates]


def saving_between(
    fit_before: SignatureFit,
    fit_after: SignatureFit,
    climatology: Climatology,
    records_before: Iterable[DailyRecord],
    records_after: Iterable[DailyRecord],
    n_boot: int = 200,
    seed: int = 42,
    season_window: Window | None = None,
    boot_step: float = 0.5,
) -> tuple[float, tuple[float, float] | None]:
    """Saving (percent) between two fits with a bootstrap 95% interval (METHODS 8.2).

    ``season_window`` defaults to the period of ``fit_before``. Returns
    ``(saving_pct, (low, high))``; the interval is None when the bootstrap produced no
    valid refits.
    """
    window = season_window or fit_before.period
    nac_before = normalized_consumption(fit_before, climatology, window)
    nac_after = normalized_consumption(fit_after, climatology, window)
    point = saving_pct(nac_before, nac_after)

    base_records = fit_records(records_before, fit_before)
    target_records = fit_records(records_after, fit_after)
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(max(0, n_boot)):
        boot_before = _bootstrap_fit(rng, base_records, fit_before, boot_step)
        boot_after = _bootstrap_fit(rng, target_records, fit_after, boot_step)
        if boot_before is None or boot_after is None:
            continue
        nac_1 = normalized_consumption(boot_before, climatology, window)
        nac_2 = normalized_consumption(boot_after, climatology, window)
        if nac_1 <= 0:
            continue
        samples.append(saving_pct(nac_1, nac_2))
    if len(samples) < 2:
        _LOGGER.debug("bootstrap produced %d valid samples, no interval", len(samples))
        return point, None
    interval = (percentile(samples, 2.5), percentile(samples, 97.5))
    return point, interval
