# ADR 0006 - Dynamic-tariff cost from each entity's own recorded statistics, not a forecast attribute

**Status:** accepted (2026-09-13); implemented in 0.2.4

## Context

Day-ahead electricity prices (Nordpool-based) are common in NL and vary enough within a day that
a heat pump's hourly cost can differ meaningfully from `daily kWh × daily mean price`. HA
integrations that expose such prices (Nordpool, ENTSO-E, Tibber-style) each shape their
forecast attributes (`raw_today`, `raw_tomorrow`, or similar) differently, with no shared schema.
Depending on those attributes would mean one adapter per price integration, breaking on any of
their schema changes, and would only ever run for a day whose forecast happened to still be
available - it is *retrospective* daily cost Heatprint needs, computed once the day is over.

## Decision

Compute dynamic-tariff cost from the price entity's own recorded **hourly statistics** (`mean`
per hour), read the same way Heatprint already reads every other HA-sensor input - via
`statistics_during_period`, exactly as `recorder_source.py` already reads generator and
HA-sensor weather series (§METHODS §2, §13.2). This requires the price entity to have
`state_class: measurement` and hourly statistics, which is how these integrations commonly
expose their *current/historical* price already, entirely separately from their forecast
attributes.

## Consequences

- No per-integration forecast-attribute adapter is needed; any price entity with ordinary
  HA statistics works, matching how weather and generator sources are already integration-agnostic.
- A day's dynamic cost is only ever computed after that day's statistics exist - fine for
  Heatprint's daily-record model, but this cannot power a same-day "should I preheat now"
  advisory; that would be a different, forecast-attribute-dependent feature, out of scope here.
- If the price entity or the generator's electric meter lacks hourly statistics for a given day
  (a heat pump with only a SCOP estimate, or a price integration that does not record
  statistics), that day silently falls back to a flat daily-mean price (`PRICE_ESTIMATED_FLAT`,
  METHODS §13.2) rather than failing.
- Unverified: which specific NL integrations record hourly statistics on their price entity
  versus only exposing forecast attributes - a ROADMAP research item, to confirm before
  implementation rather than assume.
