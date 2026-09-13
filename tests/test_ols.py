"""Pure-Python OLS and t/F quantiles."""

from __future__ import annotations

import random

import pytest

from heatprint_core.analysis.ols import f_quantile_95_1, ols, percentile, t_quantile_975


def test_exact_line() -> None:
    xs = [0.0, 1.0, 2.0, 3.0, 4.0]
    ys = [1.0 + 2.5 * x for x in xs]
    result = ols(ys, [xs])
    assert result is not None
    assert result.coefficients[0] == pytest.approx(1.0)
    assert result.coefficients[1] == pytest.approx(2.5)
    assert result.sse == pytest.approx(0.0, abs=1e-12)
    assert result.r2 == pytest.approx(1.0)
    assert result.rmse == pytest.approx(0.0, abs=1e-9)
    assert result.n == 5 and result.p == 2 and result.df == 3
    assert result.predict(10.0) == pytest.approx(26.0)


def test_known_regression_with_noise() -> None:
    # Classic textbook example: y = 2 + 3x with residuals, hand-checked.
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [5.1, 7.9, 11.2, 13.8, 17.0]
    result = ols(ys, [xs])
    assert result is not None
    # Sxx = 10, Sxy = 29.7 -> slope 2.97, intercept 11 - 2.97 x 3 = 2.09
    assert result.coefficients[1] == pytest.approx(2.97)
    assert result.coefficients[0] == pytest.approx(2.09)
    # Residuals: 0.04, -0.13, 0.2, -0.17, 0.06 -> SSE 0.091; SST 88.3
    assert result.sse == pytest.approx(0.091)
    sigma2 = 0.091 / 3
    assert result.standard_errors[1] == pytest.approx((sigma2 / 10) ** 0.5)
    assert result.r2 == pytest.approx(1 - 0.091 / 88.3)


def test_two_regressors() -> None:
    rng = random.Random(1)
    x1 = [rng.uniform(0, 10) for _ in range(200)]
    x2 = [rng.uniform(0, 5) for _ in range(200)]
    ys = [1.0 + 2.0 * a - 0.5 * b + rng.gauss(0, 0.01) for a, b in zip(x1, x2, strict=True)]
    result = ols(ys, [x1, x2])
    assert result is not None
    assert result.coefficients == pytest.approx((1.0, 2.0, -0.5), abs=0.01)
    assert result.p == 3
    assert result.r2 > 0.999


def test_singular_and_short_inputs() -> None:
    assert ols([1.0, 2.0, 3.0], [[1.0, 1.0, 1.0]]) is None  # constant regressor
    assert ols([1.0, 2.0], [[1.0, 2.0]]) is None  # too few points
    with pytest.raises(ValueError):
        ols([1.0, 2.0, 3.0], [[1.0, 2.0]])


def test_t_quantiles() -> None:
    assert t_quantile_975(1) == pytest.approx(12.706)
    assert t_quantile_975(10) == pytest.approx(2.228)
    assert t_quantile_975(30) == pytest.approx(2.042)
    assert t_quantile_975(40) == pytest.approx(2.021, abs=0.002)
    assert t_quantile_975(60) == pytest.approx(2.000, abs=0.002)
    assert t_quantile_975(120) == pytest.approx(1.980, abs=0.002)
    assert t_quantile_975(10_000) == pytest.approx(1.960, abs=0.001)
    with pytest.raises(ValueError):
        t_quantile_975(0)


def test_f_quantiles() -> None:
    assert f_quantile_95_1(1) == pytest.approx(161.4, abs=0.2)
    assert f_quantile_95_1(10) == pytest.approx(4.96, abs=0.01)
    assert f_quantile_95_1(30) == pytest.approx(4.17, abs=0.01)
    assert f_quantile_95_1(100_000) == pytest.approx(3.84, abs=0.01)


def test_percentile() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 4.0
    assert percentile(values, 50) == 2.5
    assert percentile([5.0], 97.5) == 5.0
    with pytest.raises(ValueError):
        percentile([], 50)
