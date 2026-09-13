# ADR 0001 - Calculation core independent of Home Assistant

**Status:** accepted (2026-09-13)

## Context

Heatprint must work both as a HACS integration and be usable in notebooks/CLI and possibly
other platforms. Home Assistant code is hard to test without the HA test tooling and changes
every quarter.

## Decision

All formulas, weather providers, conversions and analyses live in `heatprint_core`, a pure
Python package without HA imports. The integration in `custom_components/heatprint` only
handles configuration, recorder I/O, storage, entities and services, and calls the core.

## Consequences

- The core can be tested with pytest (synthetic house, reference case).
- The core is published on PyPI (`heatprint-core`) and listed as `requirements` in the manifest.
- Two version numbers to manage (core + integration); always released together.
