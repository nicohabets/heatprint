# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses semantic versioning.

## [Unreleased]

### Added
- Product brief, data model, config flow specification, architecture and ADRs (all
  documentation in English).
- `heatprint_core`: models, constants, flags, weather providers (KNMI, Open-Meteo),
  effective temperature presets, degree-day methods (classic, knmi14, pbl, house), heat
  conversion per generator, DHW split, meter-reading interpolation, energy-signature fit,
  normalization, comparison, forecast, CSV importer, pipeline. With tests.
- `custom_components/heatprint`: integration skeleton (manifest, const, config flow with
  subentries, strings/translations, coordinator/sensor/services scaffolding).
- Design for per-room heat allocation and cost ("Rooms"): a room demand signal (Tado/`tado_ce`
  or a compatible integration) allocates the site's daily space heat and cost across rooms,
  with an apparent per-room heat-loss fit and an unallocated bucket, plus per-m² normalization
  (specific heat loss W/(m²·K), heat/cost per m²) and a `sensor.<site>_most_expensive_room`
  ranking. Documentation only, no implementation yet: METHODS §12, DATA_MODEL
  `Room`/`DailyRoomRecord`/`RoomSignatureFit`, a `room` subentry in CONFIG_FLOW, PRODUCT_BRIEF
  scope/requirements (§6.3, F24/F25), ROADMAP 1.1.0, ADR 0005.
- Design for cost and CO₂ (METHODS §13, closing ROADMAP open item 1): the previously-unwritten
  `cost_eur`/`co2_kg` formula, plus dynamic/day-ahead electricity tariff support
  (`price_mode: dynamic`) computed from each entity's own recorded hourly statistics rather
  than a forecast attribute (ADR 0006), and a `..._avg_price_paid` sensor. F26.
- Design for ongoing data-source health checks (METHODS §14, extends F23): stuck-value,
  implausible-value, scale-drift and stalled-weather checks surfaced as HA repairs, beyond the
  existing missing-data-only `binary_sensor.<site>_data_gap`. Documentation only, no
  implementation yet.
