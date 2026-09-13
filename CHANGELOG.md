# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses semantic versioning.

## [Unreleased]

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
- PBL daily wind coefficient verified against PBL 2022 eq. 17/20: `sqrt` mode uses
  `c_sqrt = 1.0` (`T - √W`), not the hourly Informatiecode `√W/0.35`.
- Forecast heat-season sensor is space heating + DHW, as specified in DATA_MODEL 3.3.
- Coordinator also estimates a DHW baseline for `dhw_mode = measured` (fallback on
  days without a measurement).

### Fixed
- `compare_periods` with `min_dd=0` no longer returns NaN; it raises
  `InsufficientDataError` when a period has no degree days.

### Deferred
- Cost/CO₂ sensors and price-entity reads (v1.0).
- Real Heerlen four-year mindergas export (v0.2; formula reproduction is tested).
- Half-hour time-zone statistic buckets.
