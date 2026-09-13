# ADR 0003 - External statistics als opslag voor dagrecords

**Status:** geaccepteerd (2026-09-13)

## Context

Dagrecords moeten jaren teruggaan (backfill uit CSV en weerhistorie), zichtbaar zijn in
standaard HA-grafieken en entity-hernoemingen overleven. Gewone sensor-states kunnen niet met
terugwerkende kracht worden geschreven en vervuilen de recorder.

## Besluit

Alle dagmetrics worden geschreven als external long-term statistics
(`async_add_external_statistics`) met statistic ids `heatprint:<site>_<metric>`, één record per
dag (uur 00:00 lokaal). Kleine gestructureerde data (fits, klimatologie, vlaggen, baseline) gaat
in een `Store`-JSON. Sensoren tonen de actuele afgeleiden.

## Gevolgen

- Backfill en herberekening zijn idempotent (upsert per dag).
- Statistieken verschijnen in de statistics-graph-kaart en zijn exporteerbaar.
- Het Energy-dashboard kent geen "warmte"-bron; Heatprint levert eigen kaarten/voorbeelden.
- Bij verwijderen van de integratie blijven statistieken staan tot de gebruiker ze wist
  (repair "orphaned statistics" van HA/Spook).
