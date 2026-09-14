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
| 0.2.4 | Cost + CO₂ | F18 site `cost_eur`/`co2_kg` statistics, `price_mode: dynamic` (ADR 0006), room cost allocation, `cost_space_season` / `avg_price_paid` / `co2_season` | done |
| 0.2.5 | Data-source health checks | METHODS §14 `STUCK_VALUE` / `IMPLAUSIBLE_VALUE` / `SCALE_DRIFT` / `WEATHER_STALLED` as HA repairs + `open_health_checks` | done |
| 0.2.6 | First-run / device registry UX | Short confirm description; room devices inherit the discovered HA area; default names `Heatprint {room}` not `{site} {room}` | done |
| 0.3.0 | Hybrid | Heat pump generator with thermal/electric meters, heat pump share, daily COP, season 2026/27 live | planned (when the heat pump is installed) |
| 1.0.0 | HACS release | Measure effect with CI, mindergas bridge, COP curve, DHW monthly profile, repairs/diagnostics, HACS default | planned |
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
- `heatprint.clear_statistics` service (optional `generator_id`); whole-site clear
  also drops room `*_demand` / `*_t_mean` (0.2.3).
- METHODS documents the COP-curve floor of 1.0, the bootstrap 0.5 K grid, and that
  `compare_periods` raises `InsufficientDataError` when Σ dd is 0 (never NaN).
- PBL 2022 daily wind term verified: `T - √W` (`c_sqrt = 1.0`) and optional `Q/480`.
- Site and room cost/CO₂ (0.2.4): `price_entity` and `co2_entity` are read;
  `heatprint:<site>_cost` / `_co2` and `room_<id>_cost` are written; `price_mode:
  dynamic` uses recorded hourly statistics (ADR 0006) with `PRICE_ESTIMATED_FLAT`
  fallback; `cost_space_season`, `co2_season`, `avg_price_paid`, room cost sensors
  and cost ranking for `most_expensive_room` exist. Forecast-attribute adapters
  remain out of scope.
- Multi-step first-run wizard removed in 0.2.3. `ROOM_NOT_FITTED` is written when
  a room has fewer than the minimum fit days.
- METHODS §14 health-check repairs (0.2.5): `STUCK_VALUE` / `IMPLAUSIBLE_VALUE` /
  `SCALE_DRIFT` / `WEATHER_STALLED` open and auto-close HA repairs;
  `open_health_checks` is on `sensor.<site>_data_quality`.
- First-run / device registry UX (0.2.6): confirm step is a short count +
  site/weather summary; room devices inherit the discovered HA area and default
  to `Heatprint {room}` (not `{site_name} {room}`).

Still open (not this release):

1. Statistics require local midnight to fall on a whole UTC hour; time zones with a
   half-hour offset (e.g. India) are not supported. The recorder's daily buckets
   follow the HA time zone, not the site time zone.
2. Real Heerlen reference case (KNMI 380 + four gas years of mindergas export) — needs
   Nico's local export; the core reproduces the mindergas *formula* on fixture data
   within 1%. Scheduled with the v0.2 live HA run.
3. GitHub repository description and topics (`custom-integration`, `hacs-integration`,
   `homeassistant`). HACS CI ignores those two checks until they are set on the repo.
4. Strict mypy CI gate and `pytest-homeassistant-custom-component` for the HA
   shell. Still open after v0.2 (rooms shipped without the HA test plugin).
5. Post-create "Compute effect" notification after adding a measure (service exists; v1.0 UI).
6. PDF eq. 17 sun term *outside* inertia — Heatprint keeps sun inside `T_eff` (METHODS §3);
   default practical model has `include_sun` off and therefore matches PDF eq. 20.
7. A dedicated `data_gap` repair (F23) is still v1; the
   `binary_sensor.<site>_data_gap` problem entity already exists. Health-check
   repairs shipped in 0.2.5.
8. First-run weather validation is still non-blocking (offline must not stall
   setup). **0.2.3** shows the failure on the confirm step and opens a repair /
   persistent notification. Reconfigure still blocks on `cannot_connect` /
   `no_data_for_station`.
9. `import_now` is stored as `false` and has no Options control. Use
   **Import meter readings**.

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
