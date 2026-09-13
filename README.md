# Heatprint

> **The weather-corrected heat fingerprint of your home - for gas, heat pumps, hybrids and district heat.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status](https://img.shields.io/badge/status-pre--alpha-orange)

Heatprint is a Home Assistant integration (plus a standalone Python core, `heatprint-core`) that
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

Pre-alpha **v0.1.0**. The calculation core (`heatprint_core`) implements the documented
pipeline end-to-end — heat conversion, DHW split, effective temperature, four degree-day
methods, energy signature / PRISM, normalize / compare / forecast — and is covered by
pytest on mock and synthetic data. The Home Assistant integration
(`custom_components/heatprint`) is a thin shell around that core: config flow with
subentries, daily coordinator, external statistics, sensors and the documented services.

Not in this pre-alpha (see [docs/ROADMAP.md](docs/ROADMAP.md)): cost/CO₂ sensors and
price-entity reads (v1.0), the live Heerlen four-year reference case (v0.2, needs local
meter exports), and half-hour time-zone statistic buckets.

## Documentation

| Document | Contents |
|---|---|
| [docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md) | Why, for whom, scope, requirements, risks, planning |
| [docs/METHODS.md](docs/METHODS.md) | All formulas: effective temperature, degree days, heat, DHW, energy signature, forecast |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Configuration, daily records, statistics, sensors, services |
| [docs/CONFIG_FLOW.md](docs/CONFIG_FLOW.md) | Wizard, subentries, options, reconfigure |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, storage, integrations (Mermaid) |
| [docs/adr/](docs/adr/) | Architecture decision records: [core independent of Home Assistant](docs/adr/0001-core-independent-of-home-assistant.md), [no heavy dependencies](docs/adr/0002-no-heavy-dependencies.md), [external statistics as storage](docs/adr/0003-external-statistics-as-storage.md), [four methods side by side](docs/adr/0004-four-methods-side-by-side.md) |

## Repository layout

```
custom_components/heatprint/   Home Assistant integration (HACS)
heatprint_core/                Pure-Python calculation core (PyPI: heatprint-core)
tests/                         pytest suite for the core
examples/dashboards/           Dashboard YAML examples
docs/                          Product and technical documentation
```

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
