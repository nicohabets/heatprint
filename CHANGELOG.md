# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses semantic versioning.

## [Unreleased]

## [0.2.2] - 2026-09-14

### Changed
- Docs aligned with the shipped 0.2.1 first-run (one confirm, auto rooms and
  generators, non-blocking weather check), stock Lovelace dashboards (no
  apexcharts), bundled `heatprint_core`, and deferred cost / health-check items.
  CONFIG_FLOW no longer describes Steps 2–7 as a first-run wizard.
- Version lockstep is 0.2.2 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).

### Notes (code gaps, unchanged)
- Leftover multi-step wizard in `config_flow.py` is unreachable from first-run.
- Site `cost_eur` / `co2_kg` statistics and room cost sensors still deferred
  (METHODS §13 / ROADMAP open item 1). `cost_space_season` and `avg_price_paid`
  are specified only.
- METHODS §14 health-check repairs and `open_health_checks` are specified only.
- `ROOM_NOT_FITTED` is never written to stored flags.
- `import_now` has no Options control; `co2_entity` is collected but not read.
- Strict mypy / `pytest-homeassistant-custom-component` still planned.

## [0.2.1] - 2026-09-14

### Added
- **Automatic room discovery** from Home Assistant areas (METHODS §12.6).
  Areas with a `climate` entity and/or a heating-demand sensor become `room`
  subentries. Demand preference: percentage heating-power (Tado
  `*_verwarming`) → valve position → climate `hvac_action` (binary).
  Temperature comes from the area's climate entity. Zones with
  `no_heating_circuit` and empty / non-heating areas are skipped.
- Idempotent **Sync rooms from HA areas** (setup, options, first coordinator
  reload). Updates entity links; does not duplicate rooms or wipe
  `rated_output_w`, `emitter_kind` or `floor_area_m2`. Options: auto-sync
  (default on) and an exclude-area list. After sync the rooms dashboard is
  recreated; Lovelace entity cards stay `unique_id`-based (NL-safe).

### Changed
- First-run is a **single confirm** of the Home Assistant home. Site name
  comes from `zone.home` (else HA location name / "Home"); location, time
  zone and country stay silent (v0.1.3). Weather is nearest KNMI (NL) or
  Open-Meteo. Detected gas / heat-pump meters become generator subentries
  when present. Reconfigure remains the escape hatch for a second home.
- Version lockstep is 0.2.1 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).

## [0.2.0] - 2026-09-13

### Added
- **Rooms MVP** (METHODS §12 / ADR 0005). Add `room` subentries (name, demand
  entity + kind, emitter, optional area / rated output / temperature / volume,
  enable/disable). Daily demand integrals allocate `heat_space_kwh` with an
  unallocated bucket; `metered_energy` rooms bypass allocation. Room energy
  signatures reuse the site TAC/PRISM fit (no per-room wind). Flags:
  `ROOM_DEMAND_MISSING`, `ROOM_DEMAND_FROM_HISTORY`, `ROOM_WEIGHT_ASSUMED`,
  `ROOM_NOT_FITTED`, `ROOM_TEMPERATURE_MISSING`.
- Site sensors `heat_unallocated_season` and `most_expensive_room` (ranked by
  allocated **heat** this season — cost ranking waits for site `cost_eur`
  statistics). Per-room sensors: heat yesterday/season, share, apparent UA,
  specific heat loss, balance temperature, fit quality, heat/m², data quality.
  External statistics `heat_unallocated`, `room_<id>_heat` / `_demand` /
  `_t_mean`.
- Dedicated **Heatprint Rooms** Lovelace dashboard in the sidebar
  (`heatprint-<site>-rooms`). `heatprint.create_dashboard` creates or updates
  both the overview and the rooms view. Entity cards resolve `entity_id` from
  the registry by `unique_id` (`{entry_id}_{key}` or
  `{entry_id}_{room_id}_{key}`), so a Dutch UI does not show
  “entity not found”.
- Service `heatprint.fit_room_signature`. Options: allocation on/off, minimum
  room-fit days, default W/m² per emitter (labelled placeholders).

### Changed
- Version lockstep is 0.2.0 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).

### Not in this release
- Room **cost** sensors and `room_<id>_cost` statistics are skipped on purpose.
  Site `cost_eur` is still not written as a statistic (METHODS §13 / ROADMAP
  open item 1). Heat allocation does not wait for dynamic tariffs.
- METHODS §13 dynamic tariffs and §14 health-check repairs stay follow-ups.

## [0.1.4] - 2026-09-13

### Fixed
- Auto-created Lovelace dashboard no longer hardcodes English `has_entity_name`
  object ids. Entity cards resolve `entity_id` from the entity registry by
  `unique_id` (`{config_entry.entry_id}_{key}`), so a Dutch (or any non-English)
  UI language works — `sensor.thuis_ruimteverwarming_gisteren` instead of
  `sensor.thuis_space_heating_yesterday`. Sensors that are not registered yet
  are omitted (or replaced by a markdown note) instead of a dead id.
  Statistic-graph cards are unchanged (`heatprint:<site>_<metric>`). Recreate
  an existing dashboard with `heatprint.create_dashboard`.

## [0.1.3] - 2026-09-13

### Added
- First-run config flow takes location, time zone and country from the Home
  Assistant home (`hass.config`, with `zone.home` / time zone / coordinates as
  fallbacks). Step 1 only asks for a site name. Reconfigure can still change
  these values.
- After setup, a stock Heatprint Lovelace dashboard is created and shown in the
  sidebar (`heatprint-<site>`). It uses built-in cards only (no apexcharts).
  Recreate with `heatprint.create_dashboard`.
- Options-flow **Import meter readings** wizard: paste CSV or pick a file,
  auto-detect delimiter / decimal / date format / columns, preview the first
  rows, ask with dropdowns only when headers are ambiguous, then import and
  recompute. A mindergas `datum;stand` export needs zero extra questions.

### Changed
- Humans are pointed at the import wizard; `heatprint.import_readings` stays
  for automations and power users.

## [0.1.2] - 2026-09-13

### Added
- Design for per-room heat allocation and cost ("Rooms"): a room demand signal (Tado/`tado_ce`
  or a compatible integration) allocates the site's daily space heat and cost across rooms,
  with an apparent per-room heat-loss fit and an unallocated bucket, plus per-m² normalization
  (specific heat loss W/(m²·K), heat/cost per m²) and a `sensor.<site>_most_expensive_room`
  ranking. Documentation only, no implementation yet: METHODS §12, DATA_MODEL
  `Room`/`DailyRoomRecord`/`RoomSignatureFit`, a `room` subentry in CONFIG_FLOW, PRODUCT_BRIEF
  scope/requirements (§6.3, F24/F25), ROADMAP 1.1.0, ADR 0005.
- Design for cost and CO₂ (METHODS §13, closing deferred item 1 below): the previously-unwritten
  `cost_eur`/`co2_kg` formula, plus dynamic/day-ahead electricity tariff support
  (`price_mode: dynamic`) computed from each entity's own recorded hourly statistics rather
  than a forecast attribute (ADR 0006), and a `..._avg_price_paid` sensor. F26. Documentation
  only, no implementation yet.
- Design for ongoing data-source health checks (METHODS §14, extends F23): stuck-value,
  implausible-value, scale-drift and stalled-weather checks surfaced as HA repairs, beyond the
  existing missing-data-only `binary_sensor.<site>_data_gap`. Documentation only, no
  implementation yet.

## [0.1.1] - 2026-09-13

### Fixed
- HACS / Home Assistant OS install no longer depends on an unpublished PyPI package
  (`heatprint-core==0.1.0`). The calculation core is bundled at
  `custom_components/heatprint/heatprint_core/` and exposed on `sys.path` so the
  config flow can load (`from heatprint_core import ...`) without a 500 error.

### Changed
- `hacs.json` keeps the default branch visible (`hide_default_branch` is false) so a
  custom-repository install works before GitHub releases exist.
- README documents the HACS custom-repository install path (category Integration).
- Version is 0.1.1 in `manifest.json`, `pyproject.toml`, and `heatprint_core.__version__`.

## [0.1.0] - 2026-09-13

### Added
- Brand icon at `custom_components/heatprint/brand/icon.png` for HACS validation.
- Product brief, data model, config flow specification, architecture and ADRs (all
  documentation in English).
- `heatprint_core`: models, constants, flags, weather providers (KNMI, Open-Meteo),
  effective temperature presets, degree-day methods (classic, knmi14, pbl, house), heat
  conversion per generator, DHW split, meter-reading interpolation, energy-signature fit,
  normalization, comparison, forecast, CSV importer, pipeline. With tests.
- `custom_components/heatprint`: config flow with generator/measure subentries, daily
  coordinator, external statistics, site and generator sensors, services (import,
  recompute, fit, compare, measure effect, forecast, export, mindergas push,
  clear statistics).
- `DHW_BASELINE_MISSING` flag when a baseline split has no summer/rolling estimate.
- Service `heatprint.clear_statistics` to drop a removed generator's (or the site's)
  external statistics.

### Changed
- Minimum Home Assistant version is 2026.9.0 (`hacs.json`).
- PBL daily wind coefficient verified against PBL 2022 eq. 17/20: `sqrt` mode uses
  `c_sqrt = 1.0` (`T - √W`), not the hourly Informatiecode `√W/0.35`.
- Config-flow copy for the PBL wind sqrt coefficient now states the verified daily
  default of 1.0 (no longer a "placeholder until verified").
- Forecast heat-season sensor is space heating + DHW, as specified in DATA_MODEL 3.3.
- Coordinator also estimates a DHW baseline for `dhw_mode = measured` (fallback on
  days without a measurement).
- Docs aligned with ADR 0004: all four degree-day methods are always stored; `enabled`
  / `primary` only choose the main sensors and forecast. METHODS documents that an
  enabled sun term is applied inside `T_eff` (generic family), not outside inertia
  as in PBL 2022 eq. 17.

### Fixed
- `compare_periods` with `min_dd=0` no longer returns NaN; it raises
  `InsufficientDataError` when a period has no degree days.

### Deferred
- Cost/CO₂ sensors and price-entity reads (v1.0).
- Real Heerlen four-year mindergas export (v0.2; formula reproduction is tested).
- Half-hour time-zone statistic buckets.
