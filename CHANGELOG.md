# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses semantic versioning.

## [Unreleased]

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
