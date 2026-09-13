# Heatprint

> **The weather-corrected heat fingerprint of your home - for gas, heat pumps, hybrids and district heat.**
> *Het warmteprofiel van je huis, weergecorrigeerd - voor gas, warmtepomp, hybride en warmtenet.*

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

Pre-alpha. The repository currently contains the product brief, data model, config flow spec,
architecture, the calculation core with tests, and the skeleton of the Home Assistant
integration. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation (Dutch first, English before the public HACS release)

| Document | Inhoud |
|---|---|
| [docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md) | Waarom, voor wie, scope, eisen, risico's, planning |
| [docs/METHODS.md](docs/METHODS.md) | Alle formules: effectieve temperatuur, graaddagen, warmte, tapwater, energiekenlijn, prognose |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Configuratie, dagrecords, statistieken, sensoren, services |
| [docs/CONFIG_FLOW.md](docs/CONFIG_FLOW.md) | Wizard, subentries, options, reconfigure |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Componenten, dataflow, opslag, koppelingen (Mermaid) |
| [docs/adr/](docs/adr/) | Architectuurbeslissingen |

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
