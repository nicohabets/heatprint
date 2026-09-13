"""Pure-Python ordinary least squares for one or two regressors plus intercept (ADR 0002).

Solves the normal equations with Gauss-Jordan elimination on a 2x2 or 3x3 system and
returns coefficients, SSE, R2, RMSE and standard errors. Also provides the Student t
and F quantiles needed for confidence intervals (table for small degrees of freedom,
Cornish-Fisher expansion beyond).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

#: Two-sided 95% Student t quantiles (0.975) for 1..30 degrees of freedom.
_T_975_TABLE: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}
_Z_975 = 1.959964


def t_quantile_975(df: int) -> float:
    """0.975 quantile of Student's t (two-sided 95%); table up to df 30, expansion beyond."""
    if df < 1:
        raise ValueError("degrees of freedom must be >= 1")
    if df in _T_975_TABLE:
        return _T_975_TABLE[df]
    z = _Z_975
    # Cornish-Fisher expansion of the t quantile around the normal quantile.
    term1 = (z**3 + z) / (4 * df)
    term2 = (5 * z**5 + 16 * z**3 + 3 * z) / (96 * df**2)
    term3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * df**3)
    return z + term1 + term2 + term3


def f_quantile_95_1(df: int) -> float:
    """0.95 quantile of F(1, df); equals ``t_0.975(df)**2`` (asymptote 3.84)."""
    return t_quantile_975(df) ** 2


@dataclass(frozen=True)
class OlsResult:
    """Result of :func:`ols`. ``coefficients[0]`` is the intercept."""

    coefficients: tuple[float, ...]
    standard_errors: tuple[float, ...]
    sse: float
    sst: float
    r2: float
    rmse: float
    n: int
    p: int

    @property
    def df(self) -> int:
        """Residual degrees of freedom ``n - p``."""
        return self.n - self.p

    @property
    def sigma(self) -> float:
        """Residual standard error ``sqrt(SSE / (n - p))``."""
        return math.sqrt(self.sse / self.df) if self.df > 0 else float("nan")

    def predict(self, *regressors: float) -> float:
        """Prediction for one observation."""
        value = self.coefficients[0]
        for coefficient, x in zip(self.coefficients[1:], regressors, strict=True):
            value += coefficient * x
        return value


def _invert_solve(
    matrix: list[list[float]], rhs: list[float]
) -> tuple[list[float], list[list[float]]] | None:
    """Solve ``A x = b`` and return ``(x, A^-1)`` via Gauss-Jordan; None when singular."""
    size = len(matrix)
    aug = [
        row[:] + [1.0 if i == j else 0.0 for j in range(size)] + [rhs[i]]
        for i, row in enumerate(matrix)
    ]
    scale = max(abs(v) for row in matrix for v in row) or 1.0
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) <= 1e-12 * scale:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_value = aug[col][col]
        aug[col] = [v / pivot_value for v in aug[col]]
        for row in range(size):
            if row != col and aug[row][col] != 0.0:
                factor = aug[row][col]
                aug[row] = [rv - factor * cv for rv, cv in zip(aug[row], aug[col], strict=True)]
    solution = [aug[i][-1] for i in range(size)]
    inverse = [aug[i][size : 2 * size] for i in range(size)]
    return solution, inverse


def ols(y: Sequence[float], xs: Sequence[Sequence[float]]) -> OlsResult | None:
    """Fit ``y = c0 + c1 * xs[0] (+ c2 * xs[1])`` by least squares.

    ``xs`` holds zero, one or two regressor columns of the same length as ``y``.
    Returns None when the normal equations are singular (for example a regressor that
    is constant).
    """
    n = len(y)
    k = len(xs)
    p = k + 1
    if n < p + 1:
        return None
    for column in xs:
        if len(column) != n:
            raise ValueError("regressor length does not match y")

    # Normal equations X'X and X'y accumulated in one pass.
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    sum_y = 0.0
    for i in range(n):
        row = [1.0] + [float(column[i]) for column in xs]
        yi = float(y[i])
        sum_y += yi
        for a in range(p):
            xty[a] += row[a] * yi
            for b in range(a, p):
                xtx[a][b] += row[a] * row[b]
    for a in range(p):
        for b in range(a):
            xtx[a][b] = xtx[b][a]

    solved = _invert_solve(xtx, xty)
    if solved is None:
        return None
    coefficients, inverse = solved

    mean_y = sum_y / n
    sse = 0.0
    sst = 0.0
    for i in range(n):
        prediction = coefficients[0]
        for j, column in enumerate(xs):
            prediction += coefficients[j + 1] * float(column[i])
        residual = float(y[i]) - prediction
        sse += residual * residual
        sst += (float(y[i]) - mean_y) ** 2
    sse = max(0.0, sse)
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    rmse = math.sqrt(sse / n)
    df = n - p
    sigma2 = sse / df if df > 0 else float("nan")
    standard_errors = tuple(
        math.sqrt(max(0.0, sigma2 * inverse[j][j])) if df > 0 else float("nan") for j in range(p)
    )
    return OlsResult(
        coefficients=tuple(coefficients),
        standard_errors=standard_errors,
        sse=sse,
        sst=sst,
        r2=r2,
        rmse=rmse,
        n=n,
        p=p,
    )


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile ``q`` (0..100) of ``values``."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q / 100.0
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
