# ADR 0004 - Four degree-day methods side by side, house fit as primary

**Status:** accepted (2026-09-13)

## Context

Users come from mindergas (classic 18 °C, monthly factors). The PBL shows that this method
deviates structurally. A nationally calibrated method (PBL) is better than classic but not
house-specific. A house-specific fit is the most accurate but needs ≥ 30 days of data and is
less recognisable.

## Decision

All methods (`classic`, `knmi14`, `pbl`, `house`) are always computed and stored.
The user chooses the primary method for the main sensors; default `house`, with `pbl` as
fallback as long as there is no fit. Comparisons show all methods.

## Consequences

- Migration from mindergas/Degree-days without a break in the numbers (`classic` reproduces them).
- Extra storage (4 statistics instead of 1) - negligible (1 row/day).
- The UI must explain the differences between methods; the docs contain a "which method when" page.
