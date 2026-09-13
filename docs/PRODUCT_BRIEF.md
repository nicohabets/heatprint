# Product brief - Heatprint

> *Het warmteprofiel van je huis, weergecorrigeerd. Voor gas, warmtepomp, hybride en warmtenet.*

| | |
|---|---|
| Status | Concept v0.1 (september 2026) |
| Eigenaar | Nico Habets |
| Vorm | Open source (MIT): Home Assistant-integratie via HACS + Python-rekenkern (`heatprint-core`) |
| Documenten | [METHODS](METHODS.md) · [DATA_MODEL](DATA_MODEL.md) · [CONFIG_FLOW](CONFIG_FLOW.md) · [ARCHITECTURE](ARCHITECTURE.md) · [ROADMAP](ROADMAP.md) · [ADR's](adr/) |

---

## 1. Samenvatting

Heatprint beantwoordt één vraag die geen bestaand hulpmiddel goed beantwoordt:
**"Hoeveel warmte heeft mijn huis nodig, gecorrigeerd voor het weer, en wat deden mijn
maatregelen daaraan - ongeacht of ik stook op gas, een warmtepomp, een hybride combinatie,
elektrisch of een warmtenet?"**

Het rekent alle energiedragers om naar **geleverde warmte per dag**, splitst tapwater/koken af,
zet daar een **effectieve temperatuur** tegenover (wind, traagheid, optioneel zon) en levert
vier graaddagmethodes naast elkaar (klassiek/mindergas, KNMI 14 °C, PBL/KEV-SJV 2022 en een
huisgebonden fit). Daarbovenop een **energiekenlijn per stookseizoen** (PRISM-methode): helling
= warmteverlies in W/K, balanstemperatuur = stookgedrag, met betrouwbaarheidsintervallen. Zo
wordt "heeft het triple glas geholpen?" een cijfer met een marge, en blijft de analyse
vergelijkbaar wanneer de cv-ketel een hybride warmtepomp naast zich krijgt.

Alles draait lokaal in Home Assistant, met jaren historie via external statistics, gratis
weerdata (KNMI voor NL, Open-Meteo wereldwijd) en een importfunctie voor oude meterstanden.

## 2. Probleem

- **mindergas.nl** (NL-standaard voor gasgraaddagen) logt per account **óf** m³ **óf** kWh; een
  hybride woning kan er niet in. De methode (vaste stookgrens 18 °C, maandfactoren) is door
  het PBL in 2022 als structureel onnauwkeurig beoordeeld: geen wind, geen traagheid, vaste
  grens. Na het eerste halfjaar betaald lidmaatschap.
- **Home Assistant Energy-dashboard** toont verbruik, maar corrigeert niet voor weer; de
  community vraagt er al jaren om (feature request "Add degree days to Energy Dashboard",
  GitHub discussion #1746 "Support Heating Degree Days").
- **HACS "Degree-days"** (Ernst79) is een mindergas-kloon: alleen jaartotalen, één drager,
  geen warmte, geen regressie.
- **Bestaande blogs/templates** (statistics + template sensors) zijn per huis geknutseld, zonder
  historie, zonder tapwatersplitsing en zonder warmtepompen.
- De **energietransitie** maakt het probleem groter: honderdduizenden hybride installaties
  per jaar in NL; elke eigenaar wil weten of de WP het werk doet en of de isolatiestap zin had.

## 3. Doelgroep en persona's

| Persona | Situatie | Kernvraag | Wat Heatprint moet doen |
|---|---|---|---|
| **Gas-stoker** (Nico vóór de WP) | cv-ketel, slimme meter, mindergas-gebruiker | "Bespaar ik écht, of was het een zachte winter?" | mindergas-compatibel én beter; historie importeren |
| **Hybride-eigenaar** (Nico ná de WP) | ketel + WP, omschakelpunt op tarief/temperatuur | "Wat is mijn warmtevraag en hoeveel doet de WP?" | gas + WP samenvoegen tot warmte; aandeel WP; COP |
| **All-electric** | WP met (of zonder) thermische teller, evt. elektrisch bijverwarmen | "Klopt mijn SCOP, en is de warmtevraag gedaald na isolatie?" | thermisch of SCOP-geschat, gelabeld; energiekenlijn |
| **Warmtenet** | GJ-meter | "Betaal ik voor meer warmte dan mijn huis zou moeten vragen?" | GJ → kWh; zelfde analyse |
| **Renoveerder** | maatregelen plannen/verantwoorden | "Wat leverde stap X op, en wat verwacht ik van stap Y?" | maatregelen met datum; voor/na met marge |
| **Tweaker/data-liefhebber** | wil alles zien en exporteren | "Geef me de dagdata en de fit-parameters." | export, services met response-data, alle methodes |

Buiten NL: zelfde persona's met Open-Meteo als weerbron; de PBL-preset is NL-gekalibreerd,
de huisfit is universeel.

## 4. Jobs-to-be-done

1. Weergecorrigeerd vergelijken van periodes/seizoenen (simpel: kWh per graaddag; goed:
   genormaliseerd seizoensverbruik).
2. Effect van een maatregel bepalen (isolatie, lagere aanvoertemperatuur, zonering,
   warmtepomp) met betrouwbaarheidsinterval.
3. Warmtevraag volgen bij verandering van opwekker (gas → hybride → all-electric) zonder
   trendbreuk.
4. Prognose van het lopende seizoen (warmte, gas m³, kWh) op basis van klimatologie.
5. Benchmark: warmteverlies (W/K) en balanstemperatuur als vergelijkbare kengetallen tussen
   woningen en jaren.
6. Historie behouden: oude meterstanden importeren, jaren terugrekenen.
7. Mindergas-gebruikers laten overstappen zonder verlies (zelfde graaddagen reproduceren,
   optioneel blijven pushen naar mindergas).

## 5. Waardepropositie en differentiatie

| | mindergas.nl | HACS Degree-days | HA Energy | **Heatprint** |
|---|---|---|---|---|
| Meerdere dragers samen (hybride) | nee | nee | toont apart | **ja, als warmte** |
| Tapwater/koken afsplitsen | vaste waarde | vaste waarde | nee | **gemeten / baseline / vast** |
| Wind, traagheid, zon | nee | nee | nee | **ja (KNMI, PBL, huisfit)** |
| Stookgrens | vast 18 °C | vast | - | **per maand (PBL) of gefit** |
| Regressie/energiekenlijn met CI | nee | nee | nee | **ja (PRISM)** |
| Historie importeren | ja (handmatig) | nee | nee | **ja (CSV, backfill)** |
| Lokaal/privacy | cloud | lokaal | lokaal | **lokaal** |
| Buiten NL | nee | nee | ja | **ja (Open-Meteo)** |
| Benchmark met anderen | ja | nee | nee | later (opt-in, v3) |
| Kosten | lidmaatschap | gratis | gratis | **gratis, MIT** |

## 6. Scope

### 6.1 MVP (v0.1 - "werkt voor Nico's huis en voor een hybride")

- Weerbronnen: KNMI daggegevens (alle NL-stations, dichtstbijzijnde voorgesteld), Open-Meteo
  (archive + forecast `past_days`), HA-sensoren (daggemiddelden uit statistieken).
- Effectieve temperatuur: presets `none`, `knmi`, `pbl` (0,65/0,35; wind lineair of wortel;
  zon optioneel).
- Graaddagen: `classic` (mindergas-weging, stookgrens en basistemperatuur instelbaar),
  `knmi14`, `pbl` (praktisch én optimaal parameterset), `house` (fallback tot fit).
- Opwekkers: `gas_boiler`, `heat_pump` (thermisch gemeten of SCOP-geschat), `electric_heater`,
  `air_to_air`, `district_heat`, `other`; rollen `space`/`dhw`/`both`.
- Tapwater/koken: `measured`, `baseline` (zomervenster), `fixed`, `none`.
- Dagrecords als external statistics; JSON-store voor vlaggen/fits/klimatologie.
- Sensoren: effectieve temperatuur, graaddagen (dag/seizoen), warmte (dag/seizoen), kWh per
  graaddag, m³ per graaddag (mindergas-vergelijkbaar), WP-aandeel, COP, datakwaliteit.
- Energiekenlijn-fit per seizoen (helling, balanstemperatuur, R², CI) + sensoren.
- Services: `import_readings` (CSV, mindergas-export), `recompute`, `fit_signature`,
  `compare_periods`, `forecast`, `export_daily`.
- Prognose lopend seizoen (klimatologie 20 jaar).
- Config flow met wizard-keuze (gas / hybride / all-electric / warmtenet / anders), subentries
  voor opwekkers en maatregelen, options en reconfigure.
- Vertalingen NL en EN. Voorbeelddashboard (statistics-graph + apexcharts).

### 6.2 v1.0 - "voor iedereen via HACS"

- Maatregel-effect (`measure_effect`) met genormaliseerd seizoensverbruik en bootstrap-CI.
- COP-curve (temperatuurafhankelijke COP) als schatter zonder thermische teller.
- Maandprofiel voor tapwater-baseline.
- mindergas.nl-brug (`push_reading`), CO₂ en kosten per kWh warmte (prijs-entiteiten).
- Repairs/diagnostics, uitgebreide tests (`pytest-homeassistant-custom-component`).
- HACS default-repository aanvragen; documentatiesite.

### 6.3 v2.0 - "inzicht in beeld"

- Custom Lovelace-kaart: energiekenlijn-scatter met fitlijn per seizoen, maatregelmarkers,
  vergelijkingstabel per methode.
- Weekend/vakantie/aanwezigheid als regressor (occupancy-correctie).
- Warmtevraag per zone met Tado/thermostaat-"verwarmingsvermogen" als dragerloze proxy.
- Anonieme benchmark (opt-in): W/K per m² en bouwjaar, alleen geaggregeerd.
- Export naar notebook (Parquet/CSV) en een CLI in `heatprint-core`.

### 6.4 Niet in scope

- Sturing van de installatie (geen thermostaat- of warmtepompregeling).
- Facturatie/leverancierskoppelingen.
- Koeling (graaddagen voor koelen) - later mogelijk, zelfde model met omgekeerde H.
- Eigen cloud of accounts.

## 7. Functionele eisen (alle voorgestelde opties)

| # | Eis | Prio |
|---|---|---|
| F1 | Site met locatie/tijdzone; meerdere sites per installatie | MVP |
| F2 | Weerprovider KNMI (station), Open-Meteo, HA-sensoren; fallback | MVP |
| F3 | Effectieve temperatuur met presets en configureerbare coëfficiënten | MVP |
| F4 | Vier graaddagmethodes, altijd allemaal berekend; primaire methode kiesbaar | MVP |
| F5 | Opwekkers: zes soorten, drie rollen; onbeperkt aantal per site | MVP |
| F6 | Warmteconversie per soort; WP thermisch gemeten of SCOP; COP-dag | MVP |
| F7 | Tapwater/koken: vier splitsmethoden; baseline automatisch uit zomer | MVP |
| F8 | Tellerstanden → dagverbruik met interpolatie, reset- en gatdetectie | MVP |
| F9 | Dagrecords opslaan als external statistics; backfill N jaar | MVP |
| F10 | Klimatologie (20 jaar) per site; jaarlijkse verversing | MVP |
| F11 | Energiekenlijn-fit per seizoen met CI en uitschieterdetectie | MVP |
| F12 | kWh/graaddag en m³/graaddag seizoen-tot-nu per methode | MVP |
| F13 | Prognose seizoen (warmte, per drager) | MVP |
| F14 | CSV-import (mindergas-export, leverancier) met kolommapping | MVP |
| F15 | Services met response-data voor dashboards/automations | MVP |
| F16 | Maatregelen (subentry) en voor/na-effect met genormaliseerd verbruik | v1 |
| F17 | mindergas-brug (dagelijks pushen) | v1 |
| F18 | Kosten en CO₂ per kWh warmte, prijs-entiteiten | v1 |
| F19 | COP-curve en tapwater-maandprofiel | v1 |
| F20 | Custom kaart, occupancy-regressor, zoneproxy, benchmark | v2 |
| F21 | Datakwaliteitsvlaggen op elk dagrecord en in de UI | MVP |
| F22 | Vertalingen NL/EN; uitleg bij elk veld | MVP |
| F23 | Diagnostics zonder geheimen; repairs bij datagaten | v1 |

Niet-functioneel: geen telemetrie; ≤ 1 externe call per dag per site in normaal bedrijf;
dagelijkse run < 5 s; backfill 10 jaar < 2 min; werkt op HA Green/Yellow (geen numpy
vereist in de kern).

## 8. Rekenmethodes in het kort

Zie [METHODS.md](METHODS.md). Kern: `T_eff = T - c_lin·V - c_sqrt·√V + c_sun·Q`,
traagheid `TAC = 0,65·T_eff(d) + 0,35·T_eff(d-1)`, graaddagen per methode, warmte per
opwekker, DHW-splitsing, fit `Q = a + b·max(0, T_b - TAC) + c·V`, genormaliseerd
seizoensverbruik via klimatologie, prognose. Open punt: de exacte PBL-windcoëfficiënt
(placeholder, configureerbaar; huisfit is onafhankelijk hiervan).

## 9. Nauwkeurigheid en eerlijkheid

- Elke geschatte grootheid draagt een vlag (`HEAT_ESTIMATED`, `WEATHER_PROVISIONAL`, ...).
- Fits tonen n, R², RMSE en CI; onder 30 dagen geen fit.
- Vergelijkingen tonen de uitkomst voor alle methodes, zodat zichtbaar is wanneer de conclusie
  methode-afhankelijk is.
- Validatie: synthetische woning (bekende parameters terugvinden) en referentiecase Heerlen
  (mindergas reproduceren binnen 1%; vier gasjaren).

## 10. Databronnen, licenties, privacy

| Bron | Voorwaarden |
|---|---|
| KNMI daggegevens (script-API) | open data, bronvermelding KNMI |
| Open-Meteo | gratis voor niet-commercieel gebruik (CC-BY 4.0), API-key voor commercieel |
| PBL 2022, Informatiecode bijlage 3 | publieke methodiek en parameters, bronvermelding |
| mindergas.nl API | gebruikersvoorwaarden mindergas; token van gebruiker |
| Code | MIT |

Privacy: geen data verlaat het huis behalve coördinaten/station naar de weerprovider en
(optioneel) meterstanden naar mindergas op verzoek van de gebruiker.

## 11. Risico's en mitigaties

| Risico | Kans | Impact | Mitigatie |
|---|---|---|---|
| KNMI-scriptendpoint wijzigt of verdwijnt | middel | hoog (NL) | provider-abstractie, Open-Meteo fallback, KNMI Data Platform (API-key) als tweede NL-provider in v1 |
| Tapwatersplitsing onnauwkeurig bij hybride | hoog | middel | gemeten split waar mogelijk; baseline + maandprofiel; onzekerheid tonen |
| WP zonder thermische teller | hoog | middel | SCOP/COP-curve, gelabeld; aanbeveling kWh-meter + thermische teller in docs |
| HA-API-wijzigingen (subentries, statistics) | middel | middel | minimale HA-versie, CI met hassfest, snelle releases |
| Gebruikers vertrouwen op één methode | middel | middel | alle methodes tonen; primaire methode = huisfit |
| Onderhoudslast voor één maintainer | hoog | hoog | dunne HA-schil, kern goed getest, CONTRIBUTING, issues-templates, co-maintainer zoeken |
| Verkeerde conclusies bij gedragsverandering | middel | middel | maatregelcategorie bepaalt interpretatie; occupancy-regressor in v2 |

## 12. Succesmetrics

- MVP: Nico's referentiecase reproduceert mindergas binnen 1%; fit op seizoen 2025/26 met
  R² ≥ 0,85; hybride seizoen 2026/27 zonder trendbreuk in warmtevraag.
- v1 (6 maanden na release): ≥ 250 installaties (HACS-analytics), ≥ 100 GitHub-stars,
  ≥ 10 externe issues met echte data, ≥ 3 weerstations/landen buiten NL in gebruik.
- Kwaliteit: CI groen, testdekking kern ≥ 90%, geen open P1-bug > 14 dagen.

## 13. Planning (indicatief)

| Fase | Inhoud | Inspanning |
|---|---|---|
| 0 - Fundament (nu) | Naam, repo, brief, datamodel, configflow, architectuur, kernskelet met tests | 1 week |
| 1 - Kern | Providers, methodes, warmte/DHW, tellerstanden, fit, prognose; referentiecase Heerlen | 2-3 weken avondwerk |
| 2 - HA-schil MVP | Config flow, coordinator, statistieken, sensoren, services; op eigen HA draaien | 2-3 weken |
| 3 - Winter 2026/27 | Live meedraaien naast mindergas; hybride WP aansluiten; bugs; docs | doorlopend |
| 4 - v1.0 | Maatregel-effect, brug, kosten/CO₂, tests, HACS default | 3-4 weken |
| 5 - v2.0 | Kaart, occupancy, zoneproxy, benchmark | later |

## 14. Open vragen en beslissingen

1. **Naam**: Heatprint (gekozen; PyPI en GitHub vrij op 13-09-2026). Alternatieven overwogen:
   Balancepoint (concept, internationaal), Stooklijn (NL, verwarrend met "stooklijn" =
   verwarmingscurve), Graadmeter (NL-woordspeling, niet internationaal).
2. **Taal van de documentatie**: nu Nederlands (doelgroep NL-first, snelle iteratie);
   vóór de publieke HACS-release Engelse vertaling van README/docs. Code en UI-strings zijn
   tweetalig vanaf dag 1.
3. **PBL-windcoëfficiënt**: verifiëren in de pdf (Nico levert pdf aan); tot die tijd
   `linear` als standaard.
4. **Subentries vs. options-lijst**: subentries (HA ≥ 2025.3) gekozen voor beheer per
   opwekker; ouder HA wordt niet ondersteund.
5. **Publiceren van `heatprint-core` op PyPI vs. vendoren in de integratie**: PyPI (schoner,
   herbruikbaar); vendoren als noodgreep.
6. **Bijdragen aan Ernst79/degree-days in plaats van eigen project**: nee, scope te
   verschillend; wel credits en een migratiepad voor die gebruikers (zelfde `classic`-cijfers).
7. **Benchmark (opt-in)**: pas als er voldoende gebruikers zijn; vereist een kleine
   backend en privacy-ontwerp.

## 15. Bronnen

- PBL (2022), *Herziening weerscorrectie voor ruimteverwarming*.
- Informatiecode elektriciteit en gas, bijlage 3 (profielenmethodiek aardgas).
- KNMI, *Graaddagen in gasjaar 2021* (definitie 14 °C en effectieve temperatuur).
- mindergas.nl, *Over graaddagen*, *Warmtepomp en graaddagen*, FAQ.
- Fels, M. (1986), *PRISM: an introduction*, Energy and Buildings 9 - genormaliseerd verbruik
  via balanstemperatuur-regressie.
- Home Assistant developer docs: long-term statistics, external statistics, config subentries.
- Ernst79/degree-days (HACS), klausj1/homeassistant-statistics, Spook recorder-services.
