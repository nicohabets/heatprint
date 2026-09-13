# ADR 0002 - No heavy dependencies in the core

**Status:** accepted (2026-09-13)

## Context

Home Assistant also runs on small hardware (HA Green/Yellow, Raspberry Pi). numpy/scipy/pandas
are large, slow down installation and cause wheel problems on some platforms. The
calculations (OLS with one or two regressors, grid search, bootstrap over ~200 days) are
small.

## Decision

`heatprint_core` has no mandatory runtime dependencies. OLS, grid search and bootstrap are
implemented in pure Python. HTTP clients are optional (`aiohttp` via the `http` extra); in HA
the HA aiohttp session is passed in.

## Consequences

- Slightly more code of our own (least squares, t-quantiles as a table/approximation).
- Fast installation via HACS, no compilation.
- For heavy analyses outside HA a user can export the daily records to pandas.
