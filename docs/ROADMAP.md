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

## Openstaande punten uit de review van v0.1 (13-09-2026)

1. `cost_eur` en `co2_kg` worden berekend maar nog niet als statistiek/sensor geschreven;
   prijs-entiteiten worden nog niet gelezen (`core_api.build_daily_records`, v1.0).
2. Baselines worden alleen voor `dhw_mode = baseline` berekend; `measured` valt op dagen
   zonder meting terug op "geen baseline" (`coordinator.py`).
3. Statistieken vereisen dat lokale middernacht op een heel UTC-uur valt; tijdzones met een
   half uur offset (bijv. India) worden nog niet ondersteund. Dagbuckets van de recorder
   volgen de HA-tijdzone, niet de site-tijdzone.
4. `compare_periods` geeft NaN bij expliciet `min_dd=0`; COP-curve wordt op 1,0 geklemd; de
   bootstrap gebruikt een 0,5 K-raster - alle drie nog niet in METHODS vastgelegd.
5. Vlag `DHW_BASELINE_MISSING` toevoegen (METHODS §6).
6. Service `heatprint.clear_statistics` voor het opruimen van statistieken van een verwijderde
   opwekker.

## Onderzoeksitems

- Exacte PBL-windcoëfficiënt en zonterm verifiëren (pdf).
- KNMI Data Platform (EDR/open data API) als tweede NL-provider met key.
- Welke warmtepompmerken leveren thermische energie via HA-integraties (Vaillant, Viessmann,
  NIBE, Bosch/EMS-ESP, Remeha, Daikin, Mitsubishi, Panasonic) - matrix voor de docs.
- Occupancy: aanwezigheid/werkdag als regressor (HA `person`, `workday`).
