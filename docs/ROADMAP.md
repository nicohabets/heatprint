# Roadmap

| Version | Goal | Main content | Status |
|---|---|---|---|
| 0.1.0 | Foundation + calculation core | Docs, `heatprint_core` with tests (providers, methods, heat, DHW, meter readings, fit, forecast), HA shell (config flow, coordinator, sensors, services, statistics) | done |
| 0.1.1 | HACS installable without PyPI | Core bundled inside the integration; config-flow 500 from missing `heatprint-core` wheel fixed | done |
| 0.1.2 | Rooms/cost/health-check specs | Per-room heat allocation & cost design (METHODS §12), cost/CO₂ formula + dynamic tariffs (§13), data-source health checks (§14) - documentation only, no implementation | done |
| 0.1.3 | HA home defaults + auto dashboard | First-run site from HA home, stock Lovelace overview, CSV import wizard | done |
| 0.1.4 | Dashboard entity ids | Auto-dashboard resolves Lovelace entity cards by unique_id (Dutch / non-English UI) | done |
| 0.2.0 | Rooms MVP | Room subentry, demand-weighted allocation of `heat_space_kwh`, unallocated bucket, room energy signature (site TAC), room sensors + Rooms Lovelace dashboard | done |
| 0.2.1 | Runs on Nico's HA | Auto-discover rooms from HA areas + climate/demand; one-screen first-run from `zone.home`; coordinator end-to-end, KNMI 380, DSMR gas, mindergas CSV (reference case still needs local export) | rooms auto-sync done; live reference case still planned |
| 0.2.2 | Docs vs codebase audit | Align ARCHITECTURE / CONFIG_FLOW / DATA_MODEL / PRODUCT_BRIEF with shipped 0.2.1; list remaining code gaps | done (docs) |
| 0.2.3 | First-run cleanup | Delete dead wizard; surface weather-check failures; emit `ROOM_NOT_FITTED`; `clear_statistics` room means | done |
| 0.2.4 / 0.3 | Cost + health checks | Full F18 cost/CO₂ + dynamic tariffs (METHODS §13) and §14 health-check repairs — not half-implemented in 0.2.3 | planned |
| 0.3.0 | Hybrid | Heat pump generator with thermal/electric meters, heat pump share, daily COP, season 2026/27 live | planned (when the heat pump is installed) |
| 1.0.0 | HACS release | Measure effect with CI, mindergas bridge, cost/CO₂, COP curve, DHW monthly profile, repairs/diagnostics, HACS default | planned |
| 1.1.0 | Room cost | Per-room and total heating cost (needs site `cost_eur` statistics, METHODS §13) plus cost ranking for `most_expensive_room` | planned |
| 2.0.0 | Visual insight | Custom card (energy signature), occupancy regressor, export/CLI, opt-in benchmark | idea |

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

1. `cost_eur` and `co2_kg` are now specified (METHODS §13, including dynamic/day-ahead
   tariffs, §13.2) but still computed in the core only, not written as a statistic/sensor;
   price entities are not read (`core_api.build_daily_records`, F18 / v1.0).
2. Statistics require local midnight to fall on a whole UTC hour; time zones with a
   half-hour offset (e.g. India) are not supported. The recorder's daily buckets
   follow the HA time zone, not the site time zone.
3. Real Heerlen reference case (KNMI 380 + four gas years of mindergas export) — needs
   Nico's local export; the core reproduces the mindergas *formula* on fixture data
   within 1%. Scheduled with the v0.2 live HA run.
4. GitHub repository description and topics (`custom-integration`, `hacs-integration`,
   `homeassistant`). HACS CI ignores those two checks until they are set on the repo.
5. Strict mypy CI gate and `pytest-homeassistant-custom-component` for the HA
   shell. Still open after v0.2 (rooms shipped without the HA test plugin).
6. Post-create "Compute effect" notification after adding a measure (service exists; v1.0 UI).
7. PDF eq. 17 sun term *outside* inertia — Heatprint keeps sun inside `T_eff` (METHODS §3);
   default practical model has `include_sun` off and therefore matches PDF eq. 20.
8. Rooms **heat** side shipped in 0.2.0 (subentry, allocation, room fit, sensors,
   Rooms dashboard). Room **cost** sensors are skipped until site `cost_eur` is
   written as a statistic (item 1 / METHODS §13). Cost/CO₂ dynamic tariffs (§13)
   and data-source health checks (§14) are still specified only — no
   `price_mode: dynamic` handling, and no `STUCK_VALUE`/`IMPLAUSIBLE_VALUE`/
   `SCALE_DRIFT`/`WEATHER_STALLED` checks or repairs yet.
9. Leftover multi-step first-run wizard — **removed in 0.2.3**. First-run
   auto-creates generators (heat-pump role `both`) and rooms.
10. First-run weather validation is still non-blocking (offline must not stall
    setup). **0.2.3** shows the failure on the confirm step and opens a repair /
    persistent notification. Reconfigure still blocks on `cannot_connect` /
    `no_data_for_station`.
11. `import_now` is stored as `false` and has no Options control. Use
    **Import meter readings**.
12. `ROOM_NOT_FITTED` is **written in 0.2.3** when a room has fewer than the
    minimum fit days (skipped once a room fit exists).
13. Options collect `co2_entity`; the coordinator does not read it. `cost_space_season`
    and `avg_price_paid` sensors are specified but not created (item 1 / 0.2.4).
14. `heatprint.clear_statistics` (whole site) **also drops** room `*_demand` /
    `*_t_mean` mean statistics (0.2.3).

## Research items

- KNMI Data Platform (EDR/open data API) as a second NL provider with a key.
- Which heat pump brands provide thermal energy via HA integrations (Vaillant, Viessmann,
  NIBE, Bosch/EMS-ESP, Remeha, Daikin, Mitsubishi, Panasonic) - matrix for the docs.
- Occupancy: presence/workday as a regressor (HA `person`, `workday`).
- Rooms: default heat output per m² by emitter kind (radiator/underfloor), for the
  weight defaults in METHODS §12.2 - verify against manufacturer data or a published NL
  heat-loss guideline rather than shipping unverified placeholders (0.2.0 ships the
  flagged placeholders).
- Rooms: confirm the exact semantics of the Tado "heating power" percentage
  (controller demand vs. valve opening vs. duty cycle) and build an entity/attribute matrix
  for the other thermostat/TRV integrations mentioned in METHODS §12.6.
- Dynamic tariff (METHODS §13.2): confirm which NL day-ahead price integrations expose hourly
  long-term statistics on their price entity (not just live forecast attributes) - Nordpool,
  ENTSO-E and Tibber-style integrations are the likely candidates, unverified.
