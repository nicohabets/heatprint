# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses semantic versioning.

## [Unreleased]

## [0.2.5] - 2026-09-14

### Added
- METHODS §14 data-source health checks, run daily over every generator, room
  demand entity and weather source: `STUCK_VALUE`, `IMPLAUSIBLE_VALUE`,
  `SCALE_DRIFT`, `WEATHER_STALLED`. Each firing check opens a Home Assistant
  repair that names the source and what to check; the next daily pass that no
  longer fires the check closes it. Distinct from `binary_sensor.<site>_data_gap`
  (missing data), which is unchanged.
- `sensor.<site>_data_quality` now exposes `open_health_checks` (list of
  `{check, source_kind, source_id, source_name, hint}`) as specified in
  DATA_MODEL §4 / METHODS §14.
- Thresholds stay simple (no numpy, ADR 0002): 3 zero-increment days while
  another generator still shows space heat; 5× trailing 30-day median;
  10× step between two 15-day medians when degree days are comparable;
  provisional weather longer than the provider window (KNMI 2 days,
  Open-Meteo ERA5 delay 8 days).

### Changed
- Version lockstep is 0.2.5 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).

### Notes
- Cost/CO₂ (METHODS §13) already shipped in 0.2.4 on main. This release is
  only §14 health-check repairs.

## [0.2.4] - 2026-09-14

### Added
- Site `cost_eur` and `co2_kg` are written as external statistics
  (`heatprint:<site>_cost`, `heatprint:<site>_co2`) from each generator's
  `price_entity` and CO₂ factor (METHODS §13.1). Flat tariff first.
- `price_mode: dynamic` (ADR 0006): hourly cost from recorded hourly
  statistics on the price entity (`mean`) and the electric meter (`change`).
  Missing hourly series falls back to the day's mean price with flag
  `PRICE_ESTIMATED_FLAT`.
- Room cost allocation (METHODS §12.5): `room_<id>_cost` statistics,
  `room_cost_season` / `room_cost_per_m2_season` sensors.
- Sensors: `cost_space_season`, `co2_season`, and
  `avg_price_paid` (per generator, only when `price_mode: dynamic`).
- `most_expensive_room` ranks by allocated cost when cost data exists;
  heat ranking stays as `by_heat` / fallback.
- Site pricing options (`co2_entity` and gas/electric/district factors)
  are applied. Live `co2_entity` overrides electric factors per day.
- `price_entity` is shown again on room add/reconfigure (metered rooms).
  Electric generators can set `price_mode`.

### Changed
- Version lockstep is 0.2.4 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).
- DATA_MODEL, METHODS §12.5/§13, ROADMAP, CONFIG_FLOW, ARCHITECTURE and
  PRODUCT_BRIEF now describe the shipped cost/CO₂ path instead of deferring it.
  Closed audit leftovers for F18 / room cost / `co2_entity` were moved out of
  the deferred list.

## [0.2.3] - 2026-09-14

### Removed
- Unreachable multi-step first-run wizard in `config_flow.py` (`situation` →
  `generator` → DHW → methods → history → `summary`) and its unused
  translation keys / `situation` selector. First-run stays one confirm.
  Reconfigure, Options, and generator / measure / room subentries are unchanged.

### Added
- First-run weather check is still non-blocking, but no longer silent: the
  confirm step shows `cannot_connect` / `no_data_for_station`, and setup opens
  a warning repair plus a persistent notification that names the failure.
  A later successful weather fetch dismisses both.
- `ROOM_NOT_FITTED` is written on room-days when a room has fewer than the
  configured minimum fit days (skipped once a room fit exists).

### Fixed
- `heatprint.clear_statistics` (whole site) also deletes room `*_demand` and
  `*_t_mean` mean statistics, not only room heat sums.

### Changed
- Manual add/reconfigure of a room no longer shows `price_entity` (`show_price
  or True`). Cost/CO₂ sensors are still deferred (METHODS §13).
- Unused `name_exists` config-flow error string dropped.
- Version lockstep is 0.2.3 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).

### Notes (follow-up 0.2.4 / 0.3)
- Full F18 cost/CO₂ + dynamic tariffs (METHODS §13) and §14 health-check
  repairs are **not** in this PR. Do not half-implement cost.

## [0.2.2] - 2026-09-14

### Changed
- Docs aligned with the shipped 0.2.1 first-run (one confirm, auto rooms and
  generators, non-blocking weather check), stock Lovelace dashboards (no
  apexcharts), bundled `heatprint_core`, and deferred cost / health-check items.
  CONFIG_FLOW no longer describes Steps 2–7 as a first-run wizard.
- Version lockstep is 0.2.2 (`manifest.json`, `pyproject.toml`,
  `heatprint_core.__version__`).

### Notes (code gaps, unchanged)
- Site `cost_eur` / `co2_kg` statistics and room cost sensors still deferred
  (METHODS §13 / ROADMAP open item 1). `cost_space_season` and `avg_price_paid`
  are specified only.
- METHODS §14 health-check repairs and `open_health_checks` are specified only.
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
