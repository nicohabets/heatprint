# Roadmap

| Version | Goal | Main content | Status |
|---|---|---|---|
| 0.1.0 | Foundation + calculation core | Docs, `heatprint_core` with tests (providers, methods, heat, DHW, meter readings, fit, forecast), HA skeleton (config flow, sensors, services, statistics) | in progress |
| 0.2.0 | Runs on Nico's HA | Coordinator end-to-end, KNMI station 380, DSMR gas, Buienradar fallback, CSV import of mindergas export (4 gas years), reference case | planned |
| 0.3.0 | Hybrid | Heat pump generator with thermal/electric meters, heat pump share, daily COP, season 2026/27 live | planned (when the heat pump is installed) |
| 1.0.0 | HACS release | Measure effect with CI, mindergas bridge, cost/CO₂, COP curve, DHW monthly profile, repairs/diagnostics, HACS default | planned |
| 1.1.0 | Rooms | Per-room heat allocation from a demand signal (Tado/`tado_ce` or compatible integration), room energy signature (apparent per-room heat loss), per-room and total heating cost, unallocated bucket | planned |
| 2.0.0 | Visual insight | Custom card (energy signature), occupancy regressor, export/CLI, opt-in benchmark | idea |

## Definition of done per release

- Tests green (core ≥ 90% coverage), ruff/mypy clean, hassfest + HACS validation green.
- CHANGELOG updated, version in `manifest.json` and `pyproject.toml` identical.
- Docs updated (METHODS on every formula change).
- Manual smoke test on an HA installation (config flow, backfill, sensors, one service).

## Open items from the v0.1 review (2026-09-13)

1. `cost_eur` and `co2_kg` are computed but not yet written as a statistic/sensor;
   price entities are not yet read (`core_api.build_daily_records`, v1.0).
2. Baselines are only computed for `dhw_mode = baseline`; `measured` falls back to "no
   baseline" on days without a measurement (`coordinator.py`).
3. Statistics require local midnight to fall on a whole UTC hour; time zones with a
   half-hour offset (e.g. India) are not yet supported. The recorder's daily buckets
   follow the HA time zone, not the site time zone.
4. `compare_periods` returns NaN with an explicit `min_dd=0`; the COP curve is clamped at 1.0;
   the bootstrap uses a 0.5 K grid - none of the three is documented in METHODS yet.
5. Add the `DHW_BASELINE_MISSING` flag (METHODS §6).
6. Service `heatprint.clear_statistics` for cleaning up the statistics of a removed
   generator.

## Research items

- Verify the exact PBL wind coefficient and solar term (pdf).
- KNMI Data Platform (EDR/open data API) as a second NL provider with a key.
- Which heat pump brands provide thermal energy via HA integrations (Vaillant, Viessmann,
  NIBE, Bosch/EMS-ESP, Remeha, Daikin, Mitsubishi, Panasonic) - matrix for the docs.
- Occupancy: presence/workday as a regressor (HA `person`, `workday`).
- Rooms (1.1.0): default heat output per m² by emitter kind (radiator/underfloor), for the
  weight defaults in METHODS §12.2 - verify against manufacturer data or a published NL
  heat-loss guideline rather than shipping unverified placeholders.
- Rooms (1.1.0): confirm the exact semantics of the Tado "heating power" percentage
  (controller demand vs. valve opening vs. duty cycle) and build an entity/attribute matrix
  for the other thermostat/TRV integrations mentioned in METHODS §12.6.
