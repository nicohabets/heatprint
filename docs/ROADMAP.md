# Roadmap

| Version | Goal | Main content | Status |
|---|---|---|---|
| 0.1.0 | Foundation + calculation core | Docs, `heatprint_core` with tests (providers, methods, heat, DHW, meter readings, fit, forecast), HA shell (config flow, coordinator, sensors, services, statistics) | done |
| 0.1.1 | HACS installable without PyPI | Core bundled inside the integration; config-flow 500 from missing `heatprint-core` wheel fixed | done |
| 0.2.0 | Runs on Nico's HA | Coordinator end-to-end, KNMI station 380, DSMR gas, Buienradar fallback, CSV import of mindergas export (4 gas years), reference case | planned |
| 0.3.0 | Hybrid | Heat pump generator with thermal/electric meters, heat pump share, daily COP, season 2026/27 live | planned (when the heat pump is installed) |
| 1.0.0 | HACS release | Measure effect with CI, mindergas bridge, cost/CO₂, COP curve, DHW monthly profile, repairs/diagnostics, HACS default | planned |
| 2.0.0 | Visual insight | Custom card (energy signature), occupancy regressor, zone proxy (Tado), export/CLI, opt-in benchmark | idea |

## Definition of done per release

- Tests green (core ≥ 90% coverage), ruff/mypy clean, hassfest + HACS validation green.
- Minimum Home Assistant 2026.9.0 (`hacs.json`).
- CHANGELOG updated, version in `manifest.json` and `pyproject.toml` identical.
- Docs updated (METHODS on every formula change).
- Manual smoke test on an HA installation (config flow, backfill, sensors, one service).

## Open items from the v0.1 review (2026-09-13)

Closed in this pre-alpha:

- `DHW_BASELINE_MISSING` flag (METHODS §6 / §10); coordinator also estimates a baseline
  for `dhw_mode = measured` so days without a measurement can fall back.
- `heatprint.clear_statistics` service (optional `generator_id`).
- METHODS documents the COP-curve floor of 1.0, the bootstrap 0.5 K grid, and that
  `compare_periods` raises `InsufficientDataError` when Σ dd is 0 (never NaN).
- PBL 2022 daily wind term verified: `T - √W` (`c_sqrt = 1.0`) and optional `Q/480`.

Deferred (not required for a coherent pre-alpha):

1. `cost_eur` and `co2_kg` are computed in the core but not written as a statistic/sensor;
   price entities are not read (`core_api.build_daily_records`, F18 / v1.0).
2. Statistics require local midnight to fall on a whole UTC hour; time zones with a
   half-hour offset (e.g. India) are not supported. The recorder's daily buckets
   follow the HA time zone, not the site time zone.
3. Real Heerlen reference case (KNMI 380 + four gas years of mindergas export) — needs
   Nico's local export; the core reproduces the mindergas *formula* on fixture data
   within 1%. Scheduled with the v0.2 live HA run.
4. GitHub repository description and topics (`custom-integration`, `hacs-integration`,
   `homeassistant`). HACS CI ignores those two checks until they are set on the repo.
5. Strict mypy CI gate and `pytest-homeassistant-custom-component` for the HA shell (v0.2).
6. Post-create "Compute effect" notification after adding a measure (service exists; v1.0 UI).
7. PDF eq. 17 sun term *outside* inertia — Heatprint keeps sun inside `T_eff` (METHODS §3);
   default practical model has `include_sun` off and therefore matches PDF eq. 20.

## Research items

- KNMI Data Platform (EDR/open data API) as a second NL provider with a key.
- Which heat pump brands provide thermal energy via HA integrations (Vaillant, Viessmann,
  NIBE, Bosch/EMS-ESP, Remeha, Daikin, Mitsubishi, Panasonic) - matrix for the docs.
- Occupancy: presence/workday as a regressor (HA `person`, `workday`).
