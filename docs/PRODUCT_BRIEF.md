# Product brief - Heatprint

> *The weather-corrected heat fingerprint of your home. For gas, heat pumps, hybrids and district heating.*

| | |
|---|---|
| Status | Draft v0.1 (September 2026) |
| Owner | Nico Habets |
| Form | Open source (MIT): Home Assistant integration via HACS + Python calculation core (`heatprint-core`) |
| Documents | [METHODS](METHODS.md) · [DATA_MODEL](DATA_MODEL.md) · [CONFIG_FLOW](CONFIG_FLOW.md) · [ARCHITECTURE](ARCHITECTURE.md) · [ROADMAP](ROADMAP.md) · [ADRs](adr/) |

---

## 1. Summary

Heatprint answers one question that no existing tool answers well:
**"How much heat does my house need, corrected for the weather, and what did my
energy-saving measures change - regardless of whether I heat with gas, a heat pump, a hybrid
setup, electricity or district heating?"**

It converts all energy carriers into **delivered heat per day**, splits off domestic hot water
(DHW) and cooking, sets that against an **effective temperature** (wind, thermal inertia,
optionally solar) and provides four degree-day methods side by side (classic/mindergas, KNMI
14 °C, PBL/KEV-SJV 2022 and a house-specific fit). On top of that an **energy signature per
heating season** (PRISM method): slope = heat loss in W/K, balance temperature = heating
behaviour, with confidence intervals. That turns "did the triple glazing help?" into a number
with a margin, and the analysis stays comparable when the gas boiler gets a hybrid heat pump
next to it.

Everything runs locally in Home Assistant, with years of history via external statistics, free
weather data (KNMI for NL, Open-Meteo worldwide) and an import function for old meter readings.

## 2. Problem

- **mindergas.nl** (the NL standard for gas degree days) logs **either** m³ **or** kWh per
  account; a hybrid home cannot be entered. The method (fixed heating limit of 18 °C, monthly
  factors) was judged structurally inaccurate by the PBL in 2022: no wind, no thermal inertia,
  fixed limit. Paid membership after the first six months.
- The **Home Assistant Energy dashboard** shows consumption but does not correct for weather;
  the community has been asking for it for years (feature request "Add degree days to Energy
  Dashboard", GitHub discussion #1746 "Support Heating Degree Days").
- **HACS "Degree-days"** (Ernst79) is a mindergas clone: annual totals only, one carrier,
  no heat, no regression.
- **Existing blogs/templates** (statistics + template sensors) are hand-built per house, without
  history, without a DHW split and without heat pumps.
- The **energy transition** makes the problem bigger: hundreds of thousands of hybrid
  installations per year in NL; every owner wants to know whether the heat pump is doing the
  work and whether the insulation step paid off.

## 3. Target group and personas

| Persona | Situation | Key question | What Heatprint must do |
|---|---|---|---|
| **Gas user** (Nico before the heat pump) | gas boiler, smart meter, mindergas user | "Am I really saving, or was it a mild winter?" | mindergas-compatible and better; import history |
| **Hybrid owner** (Nico after the heat pump) | boiler + heat pump, switch-over point on tariff/temperature | "What is my heat demand and how much of it does the heat pump cover?" | merge gas + heat pump into heat; heat pump share; COP |
| **All-electric** | heat pump with (or without) thermal energy meter, possibly electric backup heating | "Is my SCOP right, and has the heat demand dropped after insulation?" | thermally measured or SCOP-estimated, labelled; energy signature |
| **District heating** | GJ meter | "Am I paying for more heat than my house should need?" | GJ → kWh; same analysis |
| **Renovator** | planning/justifying measures | "What did step X deliver, and what do I expect from step Y?" | measures with a date; before/after with margin |
| **Tweaker/data enthusiast** | wants to see and export everything | "Give me the daily data and the fit parameters." | export, services with response data, all methods |

Outside NL: the same personas with Open-Meteo as weather source; the PBL preset is
NL-calibrated, the house fit is universal.

## 4. Jobs-to-be-done

1. Weather-corrected comparison of periods/seasons (simple: kWh per degree day; good:
   normalized seasonal consumption).
2. Determine the effect of a measure (insulation, lower flow temperature, zoning,
   heat pump) with a confidence interval.
3. Track heat demand through a change of generator (gas → hybrid → all-electric) without
   a break in the trend.
4. Forecast for the current season (heat, gas m³, kWh) based on climatology.
5. Benchmark: heat loss (W/K) and balance temperature as comparable key figures between
   homes and years.
6. Preserve history: import old meter readings, recompute years back.
7. Let mindergas users switch without loss (reproduce the same degree days,
   optionally keep pushing to mindergas).

## 5. Value proposition and differentiation

| | mindergas.nl | HACS Degree-days | HA Energy | **Heatprint** |
|---|---|---|---|---|
| Multiple carriers combined (hybrid) | no | no | shows them separately | **yes, as heat** |
| Split off DHW/cooking | fixed value | fixed value | no | **measured / baseline / fixed** |
| Wind, thermal inertia, solar | no | no | no | **yes (KNMI, PBL, house fit)** |
| Heating limit | fixed 18 °C | fixed | - | **per month (PBL) or fitted** |
| Regression/energy signature with CI | no | no | no | **yes (PRISM)** |
| Import history | yes (manual) | no | no | **yes (CSV, backfill)** |
| Local/privacy | cloud | local | local | **local** |
| Outside NL | no | no | yes | **yes (Open-Meteo)** |
| Benchmark against others | yes | no | no | later (opt-in, v3) |
| Cost | membership | free | free | **free, MIT** |

## 6. Scope

### 6.1 MVP (v0.1 - "works for Nico's house and for a hybrid")

- Weather sources: KNMI daily data (all NL stations, nearest one suggested), Open-Meteo
  (archive + forecast `past_days`), HA sensors (daily averages from statistics).
- Effective temperature: presets `none`, `knmi`, `pbl` (0.65/0.35; wind linear or square root;
  solar optional).
- Degree days: `classic` (mindergas weighting, heating limit and base temperature configurable),
  `knmi14`, `pbl` (both the practical and the optimal parameter set), `house` (fallback until
  a fit exists).
- Generators: `gas_boiler`, `heat_pump` (thermally measured or SCOP-estimated), `electric_heater`,
  `air_to_air`, `district_heat`, `other`; roles `space`/`dhw`/`both`.
- DHW/cooking: `measured`, `baseline` (summer window), `fixed`, `none`.
- Daily records as external statistics; JSON store for flags/fits/climatology.
- Sensors: effective temperature, degree days (day/season), heat (day/season), kWh per
  degree day, m³ per degree day (mindergas-comparable), heat pump share, COP, data quality.
- Energy signature fit per season (slope, balance temperature, R², CI) + sensors.
- Services: `import_readings` (CSV, mindergas export), `recompute`, `fit_signature`,
  `compare_periods`, `forecast`, `export_daily`.
- Forecast for the current season (20-year climatology).
- Config flow with wizard choice (gas / hybrid / all-electric / district heating / other),
  subentries for generators and measures, options and reconfigure.
- Translations NL and EN. Example dashboard (statistics-graph + apexcharts).

### 6.2 v1.0 - "for everyone via HACS"

- Measure effect (`measure_effect`) with normalized seasonal consumption and bootstrap CI.
- COP curve (temperature-dependent COP) as an estimator without a thermal energy meter.
- Monthly profile for the DHW baseline.
- mindergas.nl bridge (`push_reading`), CO₂ and cost per kWh of heat (price entities).
- Repairs/diagnostics, extended tests (`pytest-homeassistant-custom-component`).
- Apply for the HACS default repository; documentation site.

### 6.3 v2.0 - "visual insight"

- Custom Lovelace card: energy signature scatter plot with fit line per season, measure
  markers, comparison table per method.
- Weekend/holiday/presence as a regressor (occupancy correction).
- Heat demand per zone with Tado/thermostat "heating power" as a carrier-less proxy.
- Anonymous benchmark (opt-in): W/K per m² and year of construction, aggregated only.
- Export to notebook (Parquet/CSV) and a CLI in `heatprint-core`.

### 6.4 Out of scope

- Controlling the installation (no thermostat or heat pump control).
- Billing/energy supplier integrations.
- Cooling (degree days for cooling) - possibly later, same model with reversed H.
- Own cloud or accounts.

## 7. Functional requirements (all proposed options)

| # | Requirement | Priority |
|---|---|---|
| F1 | Site with location/time zone; multiple sites per installation | MVP |
| F2 | Weather providers KNMI (station), Open-Meteo, HA sensors; fallback | MVP |
| F3 | Effective temperature with presets and configurable coefficients | MVP |
| F4 | Four degree-day methods, always all computed; primary method selectable | MVP |
| F5 | Generators: six types, three roles; unlimited number per site | MVP |
| F6 | Heat conversion per type; heat pump thermally measured or SCOP; daily COP | MVP |
| F7 | DHW/cooking: four split methods; baseline automatically from summer | MVP |
| F8 | Meter readings → daily consumption with interpolation, reset and gap detection | MVP |
| F9 | Store daily records as external statistics; backfill N years | MVP |
| F10 | Climatology (20 years) per site; annual refresh | MVP |
| F11 | Energy signature fit per season with CI and outlier detection | MVP |
| F12 | kWh/degree day and m³/degree day season-to-date per method | MVP |
| F13 | Season forecast (heat, per carrier) | MVP |
| F14 | CSV import (mindergas export, energy supplier) with column mapping | MVP |
| F15 | Services with response data for dashboards/automations | MVP |
| F16 | Measures (subentry) and before/after effect with normalized consumption | v1 |
| F17 | mindergas bridge (daily push) | v1 |
| F18 | Cost and CO₂ per kWh of heat, price entities | v1 |
| F19 | COP curve and DHW monthly profile | v1 |
| F20 | Custom card, occupancy regressor, zone proxy, benchmark | v2 |
| F21 | Data quality flags on every daily record and in the UI | MVP |
| F22 | Translations NL/EN; explanation for every field | MVP |
| F23 | Diagnostics without secrets; repairs on data gaps | v1 |

Non-functional: no telemetry; ≤ 1 external call per day per site in normal operation;
daily run < 5 s; 10-year backfill < 2 min; runs on HA Green/Yellow (no numpy
required in the core).

## 8. Calculation methods in brief

See [METHODS.md](METHODS.md). Core: `T_eff = T - c_lin·V - c_sqrt·√V + c_sun·Q`,
thermal inertia `TAC = 0.65·T_eff(d) + 0.35·T_eff(d-1)`, degree days per method, heat per
generator, DHW split, fit `Q = a + b·max(0, T_b - TAC) + c·V`, normalized
seasonal consumption via climatology, forecast. The authentic daily PBL wind term is
`√V` with coefficient 1.0 (verified); `linear` remains the default preset.

## 9. Accuracy and honesty

- Every estimated quantity carries a flag (`HEAT_ESTIMATED`, `WEATHER_PROVISIONAL`, ...).
- Fits show n, R², RMSE and CI; no fit below 30 days.
- Comparisons show the result for all methods, so that it is visible when the conclusion
  depends on the method.
- Validation: synthetic house (recover known parameters) and the Heerlen reference case
  (reproduce mindergas within 1%; four gas years).

## 10. Data sources, licences, privacy

| Source | Terms |
|---|---|
| KNMI daily data (script API) | open data, attribution to KNMI |
| Open-Meteo | free for non-commercial use (CC-BY 4.0), API key for commercial use |
| PBL 2022, Informatiecode annex 3 | public methodology and parameters, attribution |
| mindergas.nl API | mindergas terms of use; the user's own token |
| Code | MIT |

Privacy: no data leaves the house except coordinates/station to the weather provider and
(optionally) meter readings to mindergas at the user's request.

## 11. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| KNMI script endpoint changes or disappears | medium | high (NL) | provider abstraction, Open-Meteo fallback, KNMI Data Platform (API key) as second NL provider in v1 |
| DHW split inaccurate for hybrids | high | medium | measured split where possible; baseline + monthly profile; show uncertainty |
| Heat pump without thermal energy meter | high | medium | SCOP/COP curve, labelled; recommend kWh meter + thermal energy meter in the docs |
| HA API changes (subentries, statistics) | medium | medium | minimum HA version, CI with hassfest, quick releases |
| Users rely on a single method | medium | medium | show all methods; primary method = house fit |
| Maintenance burden for a single maintainer | high | high | thin HA shell, well-tested core, CONTRIBUTING, issue templates, look for a co-maintainer |
| Wrong conclusions when behaviour changes | medium | medium | measure category determines interpretation; occupancy regressor in v2 |

## 12. Success metrics

- MVP: Nico's reference case reproduces mindergas within 1%; fit on season 2025/26 with
  R² ≥ 0.85; hybrid season 2026/27 without a break in the heat demand trend.
- v1 (6 months after release): ≥ 250 installations (HACS analytics), ≥ 100 GitHub stars,
  ≥ 10 external issues with real data, ≥ 3 weather stations/countries outside NL in use.
- Quality: CI green, core test coverage ≥ 90%, no open P1 bug > 14 days.

## 13. Planning (indicative)

| Phase | Content | Effort |
|---|---|---|
| 0 - Foundation (now) | Name, repo, brief, data model, config flow, architecture, core skeleton with tests | 1 week |
| 1 - Core | Providers, methods, heat/DHW, meter readings, fit, forecast; Heerlen reference case | 2-3 weeks of evening work |
| 2 - HA shell MVP | Config flow, coordinator, statistics, sensors, services; run on own HA | 2-3 weeks |
| 3 - Winter 2026/27 | Run live alongside mindergas; connect the hybrid heat pump; bugs; docs | ongoing |
| 4 - v1.0 | Measure effect, bridge, cost/CO₂, tests, HACS default | 3-4 weeks |
| 5 - v2.0 | Card, occupancy, zone proxy, benchmark | later |

## 14. Open questions and decisions

1. **Name**: Heatprint (chosen; PyPI and GitHub names free on 2026-09-13). Alternatives
   considered: Balancepoint (concept, international), Stooklijn (NL, confusing because
   "stooklijn" = heating curve), Graadmeter (Dutch pun, not international).
2. **Language of the documentation**: English only. Documentation, code and UI strings are
   English; Dutch exists only as a UI translation file (`translations/nl.json`).
3. **PBL wind coefficient**: verified against PBL 2022 eq. 17/20. The daily KEV-SJV
   term is `T - √W` (`c_sqrt = 1.0`), plus optional `Q/480`. The hourly Informatiecode
   term `√W/0.35` is a different formula and is not used. Default mode stays `linear`
   (`T - V/1.5`); choose `sqrt` for the authentic daily KEV-SJV wind term.
4. **Subentries vs. options list**: subentries (HA ≥ 2026.9) chosen for management per
   generator; older HA versions are not supported.
5. **Publishing `heatprint-core` on PyPI vs. vendoring it in the integration**: PyPI (cleaner,
   reusable); vendoring as a last resort.
6. **Contributing to Ernst79/degree-days instead of a separate project**: no, the scope is too
   different; but credits and a migration path for those users (same `classic` figures).
7. **Benchmark (opt-in)**: only once there are enough users; requires a small
   backend and a privacy design.

## 15. Sources

- PBL (2022), *Herziening weerscorrectie voor ruimteverwarming* (Revision of the weather
  correction for space heating).
- Informatiecode elektriciteit en gas (Information Code for electricity and gas), annex 3
  (profile methodology for natural gas).
- KNMI, *Graaddagen in gasjaar 2021* (Degree days in gas year 2021; definition of 14 °C and
  effective temperature).
- mindergas.nl, *Over graaddagen* (About degree days), *Warmtepomp en graaddagen* (Heat pump
  and degree days), FAQ.
- Fels, M. (1986), *PRISM: an introduction*, Energy and Buildings 9 - normalized consumption
  via balance-temperature regression.
- Home Assistant developer docs: long-term statistics, external statistics, config subentries.
- Ernst79/degree-days (HACS), klausj1/homeassistant-statistics, Spook recorder services.
