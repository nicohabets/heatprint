# Heatprint

> **The weather-corrected heat fingerprint of your home - for gas, heat pumps, hybrids and district heat.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-pre--alpha-orange)

Heatprint is a Home Assistant integration (plus a standalone Python core, `heatprint_core`) that
answers one question no existing tool answers well:

**"How much heat does my house actually need, corrected for the weather, and what did my
energy-saving measures change - regardless of whether I heat with gas, a heat pump, a hybrid
setup, electricity or district heat?"**

## What it does

- Converts every energy carrier into **delivered heat per day** (gas m³, heat pump kWh
  thermal or electric × SCOP, electric heating, district heat GJ) and splits off domestic hot
  water and cooking.
- Computes an **effective outdoor temperature** (wind, thermal inertia, optional solar gain)
  and four degree-day methods side by side: classic weighted (mindergas-compatible), KNMI 14 °C,
  **PBL 2022 / KEV-SJV** (the revised Dutch national weather correction) and a **house-specific
  fit**.
- Fits an **energy signature per heating season** (PRISM method): slope = heat-loss coefficient
  in W/K, balance temperature = heating behaviour, with confidence intervals. Measure effects
  become numbers with error bars.
- Keeps the analysis **comparable through the energy transition**: when a hybrid heat pump
  joins the boiler, heat demand stays one line.
- Stores years of history as **long-term statistics** (backfill from KNMI/Open-Meteo weather
  and imported meter readings, e.g. a mindergas.nl export). Everything runs locally.

## Status

Pre-alpha **v0.2.2**. Requires Home Assistant **2026.9.0** or newer. The calculation core (`heatprint_core`) implements the documented
pipeline end-to-end — heat conversion, DHW split, effective temperature, four degree-day
methods, energy signature / PRISM, normalize / compare / forecast, and **per-room heat
allocation** (METHODS §12) — and is covered by pytest on mock and synthetic data. The Home Assistant integration
(`custom_components/heatprint`) is a thin shell around that core: a one-screen first-run
that reuses the HA home and heated areas, config flow with
subentries (including auto-synced rooms), daily coordinator, external statistics, sensors and the documented services.
The core is **bundled inside the integration** so a HACS install on Home Assistant OS
does not need a PyPI package.

Not in this pre-alpha (see [docs/ROADMAP.md](docs/ROADMAP.md)): room/site cost sensors and
price-entity reads (v1.0 / §13), data-source health-check repairs (§14), the live Heerlen
four-year reference case (needs local meter exports), and half-hour time-zone statistic buckets.

## Installation (HACS)

Heatprint is a custom integration. It is not in the HACS default store yet.

1. In Home Assistant, open **HACS**.
2. Open the three-dot menu → **Custom repositories**.
3. Add repository URL `https://github.com/nicohabets/heatprint` with category **Integration**.
4. Find **Heatprint** in HACS and **Download**.
5. **Restart** Home Assistant.
6. Go to **Settings → Devices & services → Add integration** and search for **Heatprint**.
   Confirm the Home Assistant home (name, location, time zone and country are
   taken from `zone.home` / `hass.config`; they are not asked again). Heated
   HA areas become rooms automatically (climate + heating-power sensor; Tado
   zones with `no_heating_circuit` are skipped). After setup a **Heatprint**
   overview and a **Heatprint Rooms** dashboard appear in the sidebar. Import
   old meter readings from **Configure → Import meter readings** (paste a CSV
   or pick a file; a mindergas.nl `datum;stand` export needs no extra
   questions). Recreate both dashboards with `heatprint.create_dashboard`.

Requires Home Assistant **2026.9.0** or newer. The calculation core ships inside
`custom_components/heatprint/heatprint_core/`; you do not install anything from PyPI.

## Documentation

| Document | Contents |
|---|---|
| [docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md) | Why, for whom, scope, requirements, risks, planning |
| [docs/METHODS.md](docs/METHODS.md) | All formulas: effective temperature, degree days, heat, DHW, energy signature, forecast |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Configuration, daily records, statistics, sensors, services |
| [docs/CONFIG_FLOW.md](docs/CONFIG_FLOW.md) | Wizard, subentries, options, reconfigure |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, storage, integrations (Mermaid) |
| [docs/adr/](docs/adr/) | Architecture decision records: [core independent of Home Assistant](docs/adr/0001-core-independent-of-home-assistant.md), [no heavy dependencies](docs/adr/0002-no-heavy-dependencies.md), [external statistics as storage](docs/adr/0003-external-statistics-as-storage.md), [four methods side by side](docs/adr/0004-four-methods-side-by-side.md), [room heat allocation](docs/adr/0005-room-heat-allocation-not-design-heat-loss.md), [dynamic tariff from recorded statistics](docs/adr/0006-dynamic-tariff-from-recorded-statistics-not-forecast.md) |

## Repository layout

```
custom_components/heatprint/                 Home Assistant integration (HACS)
custom_components/heatprint/heatprint_core/  Pure-Python calculation core (bundled)
tests/                                       pytest suite for the core
examples/dashboards/                         Copies of the auto-created overview and Rooms dashboards
docs/                                        Product and technical documentation
```

`from heatprint_core import ...` still works: development uses `pip install -e .`
(and pytest `pythonpath`); Home Assistant uses a small `sys.path` bootstrap so the
nested package is importable after a HACS copy.

HACS validation in CI ignores GitHub-only metadata (`topics`, `description`). Before a
HACS default submission, set a repository description and topics such as
`custom-integration`, `hacs-integration` and `homeassistant`.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,http]"
pytest
ruff check .
```

## Acknowledgements

- PBL Netherlands Environmental Assessment Agency, *Herziening weerscorrectie voor
  ruimteverwarming* (2022) - the KEV-SJV method and monthly parameters.
- KNMI for open daily station data; Open-Meteo for worldwide reanalysis data.
- mindergas.nl and the HACS *Degree-days* integration (Ernst79) for the classic weighted
  degree-day convention that Heatprint reproduces for compatibility.
- M. Fels, *PRISM: an introduction* (1986) for the balance-point regression method.

## License

MIT - see [LICENSE](LICENSE).
