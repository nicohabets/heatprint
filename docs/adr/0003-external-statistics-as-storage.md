# ADR 0003 - External statistics as storage for daily records

**Status:** accepted (2026-09-13)

## Context

Daily records must go back years (backfill from CSV and weather history), be visible in
standard HA graphs and survive entity renames. Regular sensor states cannot be written
retroactively and pollute the recorder.

## Decision

All daily metrics are written as external long-term statistics
(`async_add_external_statistics`) with statistic ids `heatprint:<site>_<metric>`, one record per
day (hour 00:00 local). Small structured data (fits, climatology, flags, baseline) goes into a
`Store` JSON. Sensors show the current derived values.

## Consequences

- Backfill and recomputation are idempotent (upsert per day).
- Statistics appear in the statistics-graph card and can be exported.
- The Energy dashboard has no "heat" source; Heatprint provides its own cards/examples.
- When the integration is removed, statistics remain until the user deletes them
  (the "orphaned statistics" repair of HA/Spook).
