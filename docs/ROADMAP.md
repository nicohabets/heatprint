# Roadmap

| Versie | Doel | Belangrijkste inhoud | Status |
|---|---|---|---|
| 0.1.0 | Fundament + rekenkern | Docs, `heatprint_core` met tests (providers, methodes, warmte, DHW, tellerstanden, fit, prognose), HA-skelet (config flow, sensoren, services, statistieken) | in uitvoering |
| 0.2.0 | Draait op Nico's HA | Coordinator end-to-end, KNMI-station 380, DSMR-gas, Buienradar-fallback, CSV-import mindergas-export (4 gasjaren), referentiecase | gepland |
| 0.3.0 | Hybride | Warmtepomp-opwekker met thermische/elektrische tellers, WP-aandeel, COP-dag, seizoen 2026/27 live | gepland (bij installatie WP) |
| 1.0.0 | HACS-release | Maatregel-effect met CI, mindergas-brug, kosten/CO₂, COP-curve, DHW-maandprofiel, repairs/diagnostics, EN-docs, HACS default | gepland |
| 2.0.0 | Inzicht in beeld | Custom kaart (energiekenlijn), occupancy-regressor, zoneproxy (Tado), export/CLI, opt-in benchmark | idee |

## Definition of done per release

- Tests groen (kern ≥ 90% dekking), ruff/mypy schoon, hassfest + HACS-validatie groen.
- CHANGELOG bijgewerkt, versie in `manifest.json` en `pyproject.toml` gelijk.
- Docs bijgewerkt (METHODS bij elke formulewijziging).
- Handmatige smoke-test op een HA-installatie (config flow, backfill, sensoren, één service).

## Onderzoeksitems

- Exacte PBL-windcoëfficiënt en zonterm verifiëren (pdf).
- KNMI Data Platform (EDR/open data API) als tweede NL-provider met key.
- Welke warmtepompmerken leveren thermische energie via HA-integraties (Vaillant, Viessmann,
  NIBE, Bosch/EMS-ESP, Remeha, Daikin, Mitsubishi, Panasonic) - matrix voor de docs.
- Occupancy: aanwezigheid/werkdag als regressor (HA `person`, `workday`).
