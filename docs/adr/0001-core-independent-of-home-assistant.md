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
- For HACS / Home Assistant OS the core is **nested** at
  `custom_components/heatprint/heatprint_core/` and shipped with the integration.
  The integration puts that directory on `sys.path` so `from heatprint_core import ...`
  keeps working. `manifest.json` does not list an unpublished PyPI requirement.
- The core remains HA-free source; only the distribution layout is nested.
- Publishing `heatprint-core` on PyPI is a later option (notebooks/CLI), not a
  prerequisite for installing the integration.
- One version number in `manifest.json` and `pyproject.toml` (released together).
