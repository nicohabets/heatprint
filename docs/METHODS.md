# Rekenmethodes (METHODS)

Dit document is de normatieve specificatie van alle berekeningen in `heatprint_core`.
Code volgt dit document; afwijkingen worden hier eerst vastgelegd.

Alle dagwaarden zijn per **lokale kalenderdag** van de site (tijdzone van de site).
Eenheden: temperatuur in °C, windsnelheid in m/s, globale straling in J/cm² per dag,
energie in kWh, gas in m³, warmte (warmtenet) in GJ.

---

## 1. Constanten en conversies

| Naam | Waarde | Toelichting |
|---|---|---|
| `GAS_HS_KWH_PER_M3` | 8,792 | Bovenwaarde Groningen-kwaliteit aardgas: 31,65 MJ/m³. NL-leveranciers factureren op bovenwaarde. |
| `GAS_HI_KWH_PER_M3` | 7,92 | Onderwaarde (ca. 28,5 MJ/m³), alleen voor gebruikers die op onderwaarde willen rekenen. |
| `GJ_TO_KWH` | 277,78 | 1 GJ = 277,78 kWh. |
| `MJ_M2_TO_J_CM2` | 100 | 1 MJ/m² = 100 J/cm² (Open-Meteo dagsom naar KNMI-eenheid). |
| `WH_M2_TO_J_CM2` | 0,36 | 1 Wh/m² = 0,36 J/cm² (Open-Meteo uursom naar KNMI-eenheid). |
| `KMH_TO_MS` | 1/3,6 | Open-Meteo wind in km/h naar m/s. |
| `KNMI_TENTHS` | 0,1 | KNMI `TG` (0,1 °C) en `FG` (0,1 m/s) zijn tienden. `Q` is al J/cm². |
| `GAS_CO2_KG_PER_M3` | 1,78 | Standaard emissiefactor aardgas NL (configureerbaar). |
| `ELEC_CO2_KG_PER_KWH` | 0,30 | Standaard emissiefactor stroom NL (configureerbaar, of live via een CO₂-sensor). |
| `W_PER_K_FROM_KWH_PER_K_DAY` | 1000/24 | kWh/(K·dag) naar W/K. |

---

## 2. Weerinvoer per dag

Elke weerprovider levert een `DailyWeather`:

| Veld | Type | Bron KNMI | Bron Open-Meteo | Bron HA-sensoren |
|---|---|---|---|---|
| `date` | date | `YYYYMMDD` | `time` | statistiekperiode |
| `t_mean` | °C | `TG` × 0,1 | uurgemiddelde `temperature_2m` | daggemiddelde van `mean` |
| `wind_mean` | m/s | `FG` × 0,1 | uurgemiddelde `wind_speed_10m` (km/h → m/s) | daggemiddelde (eenheid uit sensor) |
| `radiation` | J/cm² | `Q` | uursom `shortwave_radiation` (Wh/m² × 0,36) of dagsom `shortwave_radiation_sum` (MJ/m² × 100) | dagsom/gemiddelde × 24 × 0,36 |
| `t_min`, `t_max` | °C | `TN`, `TX` × 0,1 | `temperature_2m_min/max` | `min`/`max` |
| `provisional` | bool | laatste 1-2 dagen | model i.p.v. reanalyse (forecast-API `past_days`) | onvolledige dag |
| `source` | str | `knmi:380` | `open_meteo:50.87,5.99` | `ha:sensor.x` |

Ontbrekende `wind_mean` of `radiation` mag `None` zijn; methodes die ze nodig hebben vallen dan
terug op de temperatuur-only variant en zetten de vlag `WEATHER_PARTIAL`.

---

## 3. Effectieve temperatuur (familie)

Alle methodes gebruiken één generieke definitie met een preset:

```
T_eff(d) = t_mean(d) - c_lin * wind_mean(d) - c_sqrt * sqrt(wind_mean(d)) + c_sun * radiation(d)
TAC(d)   = w_0 * T_eff(d) + w_1 * T_eff(d-1)          (traagheidsweging, w_0 + w_1 = 1)
```

| Preset | `c_lin` | `c_sqrt` | `c_sun` | `w_0` / `w_1` | Herkomst |
|---|---|---|---|---|---|
| `none` | 0 | 0 | 0 | 1 / 0 | Kale etmaaltemperatuur (mindergas, klassieke graaddagen). |
| `knmi` | 1/1,5 | 0 | 0 | 1 / 0 | KNMI/GTS "effectieve temperatuur" (T - wind/1,5), gebruikt voor de gasjaar-graaddagen. |
| `pbl` | zie noot | zie noot | 1/480 (optioneel, standaard uit) | 0,65 / 0,35 | PBL 2022, KEV-SJV-methodiek: traagheid 0,65/0,35, wind als wortel van de windsnelheid, zon als 1/480 van de dagstraling (alleen in het "optimale" model). |
| `house` | gefit | 0 | gefit (optioneel) | 0,65 / 0,35 (of gefit) | Huisgebonden fit, zie §7. |

**Noot PBL-windterm.** Het PBL-rapport neemt wind mee "als wortel van de windsnelheid"; de exacte
coëfficiënt kon bij het schrijven van deze spec niet betrouwbaar uit de pdf worden overgenomen.
De profielenmethodiek aardgas (Informatiecode, bijlage 3) hanteert per uur een term
`sqrt(wind)/0,35`. Tot dit geverifieerd is (issue "PBL wind coefficient"):

- `pbl_wind_mode = "linear"` (standaard): `c_lin = 1/1,5`, `c_sqrt = 0`
- `pbl_wind_mode = "sqrt"`: `c_lin = 0`, `c_sqrt = PBL_WIND_SQRT_COEF` (configureerbaar, placeholder 1/0,35 uit de Informatiecode)

De huisgebonden fit (§7) schat de windgevoeligheid zelf en is daarom de aanbevolen methode
voor één woning; de PBL-preset is een landelijk gekalibreerde referentie.

Dag `d-1` ontbreekt (eerste dag van de reeks): gebruik `TAC(d) = T_eff(d)` en vlag `WEATHER_PARTIAL`.

---

## 4. Graaddagmethodes

Elke methode levert per dag een getal `dd[method]` ≥ 0. Alle methodes zijn altijd berekend en
opgeslagen; de gebruiker kiest welke hij toont.

### 4.1 `classic` - klassieke (gewogen) graaddagen, mindergas-compatibel

```
if t_ref(d) < T_limit:  DD = max(0, T_base - t_ref(d))  else 0
WDD = DD * w_month
```

- `t_ref` = `t_mean` (standaard, mindergas-compatibel) of `T_eff` van een gekozen preset.
- `T_base` = 18,0 °C (mindergas: "gemiddelde binnentemperatuur"), `T_limit` = 18,0 °C
  (mindergas: "stookgrens"; gebruikers kiezen vaak 15,5 °C).
- Maandfactoren `w_month` (mindergas-weging): nov-feb 1,1; mrt en okt 1,0; apr-sep 0,8.
  Uitschakelbaar (`weighted=false` geeft ongewogen graaddagen).

Doel: 1-op-1 vergelijkbaar met mindergas.nl en met de HACS-integratie "Degree-days".

### 4.2 `knmi14` - KNMI gasjaar-graaddagen

```
DD = max(0, 14 - T_eff_knmi(d))
```

Gasjaar loopt van 1 oktober t/m 30 september. Doel: aansluiten bij de landelijke
KNMI-publicaties over "graaddagen in het gasjaar".

### 4.3 `pbl` - PBL 2022 / KEV-SJV (praktisch model)

```
DD = RER_m * max(0, TST_m - TAC_pbl(d))     [+ TOP_m indien include_top]
```

Maandparameters (PBL Tabel 3.4, praktisch model, De Bilt, temperatuur + wind, 1 dag historie):

| Maand | TST (°C) | RER | TOP |
|---|---|---|---|
| dec, jan, feb | 17,01 | 1,00 | 1,30 |
| mrt, nov | 15,26 | 1,02 | 1,30 |
| apr, okt | 15,10 | 0,79 | 1,30 |
| mei t/m sep | 13,92 | 0,61 | 1,30 |

Alternatieve parameterset `pbl_optimal` (Tabel 3.3, 6 stations + zon): TST 14,91 / 15,09 / 15,52 /
15,15; RER 1,00 / 0,96 / 0,82 / 0,73; TOP 1,32.

- `include_top` standaard **uit**: TOP is het temperatuuronafhankelijke deel (tapwater, koken) en
  wordt in Heatprint apart behandeld (§6). Voor de weerscorrectie van ruimteverwarming hoort TOP
  er niet in (PBL doet dit ook: vergelijking zonder TOP voor de sectortoepassing).
- De maandparameters zijn landelijk (profielcategorie G1A, 2015-2020). Voor één woning zijn ze
  indicatief; zie `house`.

### 4.4 `house` - huisgebonden graaddagen

```
DD = max(0, T_b - TAC_house(d))
```

`T_b` (balanstemperatuur) en de windgevoeligheid komen uit de energiekenlijn-fit (§7) van het
meest recente stookseizoen met voldoende data. `TAC_house` is **altijd** de huis-preset
(0,65/0,35-weging, zonder windterm; de wind zit in de fit als aparte regressor), zodat de basis
van de fit niet verandert vóór en ná het fitten. Zolang er geen fit is, valt alleen de
graaddagwaarde terug: `DD = max(0, 15,5 - TAC_pbl)` met vlag `HOUSE_NOT_FITTED`.

---

## 5. Van energiedrager naar warmte

Per `Generator` (warmteopwekker) per dag:

| Soort (`kind`) | Invoer | Warmte totaal `Q_total` | Elektrisch `E_el` |
|---|---|---|---|
| `gas_boiler` | `V` m³ | `V * HV * eta` (HV = `GAS_HS_KWH_PER_M3` of Hi; `eta` standaard 0,95) | 0 |
| `heat_pump` | `E_th` kWh (thermisch, gemeten) en/of `E_el` kWh | `E_th` indien gemeten; anders `E_el * SCOP` (SCOP standaard 3,5; "geschat" gelabeld) | `E_el` |
| `electric_heater` | `E_el` kWh | `E_el * 1,0` | `E_el` |
| `air_to_air` | `E_el` kWh | `E_el * COP` (COP standaard 3,0) | `E_el` |
| `district_heat` | `H` GJ (of kWh) | `H * 277,78 * eta` (eta standaard 1,0) | 0 |
| `other` | `x` | `x * factor` | 0 of `x` |

Regels:

- Cumulatieve tellerstanden worden eerst omgezet naar dagverbruik (§9).
- Als voor een warmtepomp zowel `E_th` als `E_el` gemeten zijn: `COP_day = E_th / E_el`
  (alleen rapporteren als `E_el > 0,2 kWh`).
- Warmtepomp met alleen `E_el` en `air_to_air` (COP-geschat): `Q_total` krijgt de vlag
  `HEAT_ESTIMATED`. Optioneel (`cop_curve`): COP op basis van `t_mean`
  (`COP = cop_curve_a + cop_curve_b * t_mean`, standaard a = 2,2 en b = 0,08).
- Hybride = `gas_boiler` + `heat_pump` op dezelfde site; niets speciaals in de conversie.

---

## 6. Tapwater- en kooksplitsing (DHW)

Per generator met `role = both` wordt `Q_total` gesplitst in `Q_dhw` en `Q_space`:

| `dhw_mode` | Regel |
|---|---|
| `measured` | `Q_dhw` uit een aparte sensor (bijv. warmtepomp meldt "tapwater kWh"); `Q_space = Q_total - Q_dhw` (min 0). |
| `baseline` (standaard) | `B` = gemiddeld dagverbruik van de drager over het **zomervenster** (standaard 1 juni t/m 31 augustus van de laatste volledige zomer, minimaal 30 dagen). `Q_dhw = min(Q_total, B * conversie)`, `Q_space = Q_total - Q_dhw`. Geen zomer beschikbaar: laagste voortschrijdend 30-daags gemiddelde in de reeks. |
| `fixed` | Vaste waarde per dag (in dragereenheid of kWh), door gebruiker opgegeven (mindergas-stijl "maandverbruik warm water en koken" / 30). |
| `none` | Alles is ruimteverwarming. |

`role = dhw`: `Q_space = 0`. `role = space`: `Q_dhw = 0`.
De baseline `B` staat in **dragereenheden** (m³/dag, kWh/dag, GJ/dag; thermisch gemeten
warmtepompen: kWh_th/dag) en wordt per dag omgerekend met de werkelijke conversie van die dag
(`Q_total / drager`), wat bij vaste rendementen gelijk is aan `B * conversie`. Is er geen
baseline (minder dan 30 zomerdagen), dan telt alle warmte als ruimteverwarming; v0.2 voegt
hiervoor de vlag `DHW_BASELINE_MISSING` toe.
Baseline wordt per generator berekend en als `dhw_baseline_per_day` opgeslagen (sensor).
v2: maandprofiel voor de baseline (koud-waterinlaat varieert; zomer ≈ 0,85 × winter).

---

## 7. Energiekenlijn-fit (PRISM-achtig)

Doel: per periode (meestal een stookseizoen) het model

```
Q_space(d) = a + b * H(d) + c * wind_mean(d)        met H(d) = max(0, T_b - TAC(d))
```

fitten met kleinste kwadraten, waarbij `T_b` via raster-zoek wordt bepaald.

Procedure:

1. Selecteer dagen in de periode zonder uitsluitingsvlaggen (`ENERGY_MISSING`, `PARTIAL_DAY`,
   `WEATHER_MISSING`, `OUTLIER`). Minimaal `n >= 30`, waarvan minimaal 15 met `H > 0`.
2. Voor `T_b` in `[6,0 ; 22,0]` stap 0,1: bereken `H(d)`, doe OLS (met of zonder `c`),
   bewaar SSE. Kies `T_b` met minimale SSE. `TAC` gebruikt preset `pbl`-weging (0,65/0,35)
   zonder windterm; de windgevoeligheid zit in `c` (optie `fit_wind`, standaard aan).
3. Rapporteer: `T_b`, `a`, `b`, `c`, `r2`, `rmse = sqrt(SSE/n)`, `sse`, `n`,
   `n_heating_days`, `outliers`, `UA = b * 1000/24` (W/K), `ci95_b = b ± t(n-p) * SE(b)`
   (p = aantal parameters: 2 zonder, 3 met windterm), `ci95_Tb` uit het profiel
   (alle `T_b` waarvoor `SSE <= SSE_min * (1 + F_0,95(1, n-p)/(n-p))`).
4. Uitschieters: na de eerste fit dagen met `|residu| > 4 * rmse` markeren als `OUTLIER` en
   éénmaal herfitten.

Interpretatie in de UI:

- `b` (kWh per K per dag) en `UA` (W/K): warmteverlies van de woning. Daalt bij isolatie.
- `T_b`: balanstemperatuur. Daalt bij lagere thermostaatinstelling, meer interne warmte,
  betere zonwinst-benutting. Stijgt bij hogere setpoints.
- `a`: temperatuuronafhankelijk restant (moet ≈ 0 zijn als DHW-splitsing klopt).

---

## 8. Genormaliseerd verbruik, vergelijking en prognose

### 8.1 Klimatologie

`TAC_clim(doy)` = gemiddelde `TAC` per dag-van-het-jaar over de referentiejaren
(standaard laatste 20 jaar, KNMI heeft dit; Open-Meteo vanaf 1940). Ook `dd_clim[method](doy)`
en `wind_clim(doy)`. Kalender met 366 slots (schrikkeljaar); slot 60 bundelt 28/29 februari en
1 maart zodat elk jaar dezelfde slots vult. Opgeslagen per site (met `tac_preset` en het aantal
samples per slot) en jaarlijks ververst.

### 8.2 Genormaliseerd seizoensverbruik (NAC)

Voor een fit `(a, b, c, T_b)` over een seizoenvenster:

```
NAC = Σ_doy [ a + b * max(0, T_b - TAC_clim(doy)) + c * wind_clim(doy) ]
```

Besparing tussen fit 1 (voor) en fit 2 (na): `S = (NAC_1 - NAC_2) / NAC_1`.
Betrouwbaarheidsinterval: bootstrap (200 resamples van dagen, seed vast) op beide fits;
rapporteer 2,5% en 97,5% percentiel van `S`.

### 8.3 Eenvoudige periodevergelijking (mindergas-stijl)

```
k_i = Q_space(periode_i) / Σ dd[method](periode_i)
Δ% = (k_2 - k_1) / k_1
```

Eisen: beide periodes ≥ 30 dagen en Σ dd ≥ 100 (classic) of ≥ 50 (overige methodes). Bij te
weinig data geeft de kern een `InsufficientDataError` (geen halve `Comparison`).
Beschikbaar voor elke methode zodat de gebruiker kan zien hoe methodekeuze de uitkomst beïnvloedt.

### 8.4 Maatregel-effect

Een `Measure` heeft een datum. Vergelijking = seizoen(en) vóór vs. seizoen(en) ná, met
§8.2 (primair) en §8.3 (secundair). Overlappende maatregelen binnen één seizoen worden
gezamenlijk gerapporteerd (kan niet worden uitgesplitst; UI zegt dat expliciet).

### 8.5 Prognose lopend seizoen

```
DD_rest             = Σ dd_clim[method](doy) over resterende seizoensdagen
Q_space_forecast    = Q_space_ytd + k_ytd * DD_rest
Q_dhw_forecast      = Q_dhw_ytd + Q_dhw_per_dag * dagen_rest
Q_forecast          = Q_space_forecast + Q_dhw_forecast
```

met `k_ytd = Q_space_ytd / Σ dd_ytd`. Ruimteverwarming en tapwater worden apart voorspeld en
gerapporteerd. Als er een geldige fit is, tweede variant `Q_space_forecast_fit` met het
§8.2-model over `TAC_clim`. Per drager: `Q_forecast` verdeeld naar aandeel van de laatste 28
dagen (hybride: gas m³ en WP kWh apart). Rapporteer ook `method`, `k_ytd` en `days_remaining`.

---

## 9. Tellerstanden naar dagverbruik

Invoer: reeks `(timestamp, cumulatieve stand)` (HA long-term statistics `sum`/`state`, of
CSV-import). Uitvoer: verbruik per lokale dag.

1. Sorteer, verwijder duplicaten, detecteer resets (`stand daalt`): nieuwe reeks starten.
   De dag van de reset krijgt de som van de gemeten delen vóór en ná de reset en de vlag
   `METER_RESET`; dagen die volledig binnen een gat rond de reset vallen ontbreken.
2. Interpoleer lineair de stand op elke dag-grens (00:00 lokaal).
3. Dagverbruik = stand(d+1 00:00) - stand(d 00:00).
4. Gat tussen twee metingen > 3 dagen: alle dagen erin krijgen `INTERPOLATED`.
5. Eerste/laatste dag met onvolledige dekking: `PARTIAL_DAY`.

---

## 10. Datakwaliteitsvlaggen

| Vlag | Betekenis | Effect |
|---|---|---|
| `WEATHER_MISSING` | geen weerdata | uitgesloten van fit en k-berekening |
| `WEATHER_PARTIAL` | wind/zon/d-1 ontbreekt | methode valt terug; toegestaan in fit |
| `WEATHER_PROVISIONAL` | voorlopige weerdata | wordt later overschreven |
| `ENERGY_MISSING` | geen enkele opwekker heeft data, of een opwekker mist data binnen zijn eigen datumbereik (een later geïnstalleerde warmtepomp maakt de gashistorie dus niet ongeldig) | uitgesloten |
| `PARTIAL_DAY` | onvolledige dekking | uitgesloten |
| `INTERPOLATED` | verbruik uit lange interpolatie | toegestaan, gewicht 1 (v2: lager gewicht) |
| `METER_RESET` | tellerreset | uitgesloten |
| `HEAT_ESTIMATED` | WP-warmte via SCOP | toegestaan, gelabeld |
| `HOUSE_NOT_FITTED` | geen huisfit | `house` = fallback |
| `OUTLIER` | residu > 4 × rmse | uitgesloten na herfit |
| `IMPORTED` | uit CSV | informatief |

---

## 11. Validatie (definition of done voor de rekenkern)

- Unit tests per formule met handmatig gecontroleerde voorbeelden (o.a. KNMI-tienden,
  mindergas-weging, PBL-maandparameters, DHW-baseline, tellerinterpolatie, reset).
- Synthetische woning: genereer 2 seizoenen met bekende `(a, b, T_b)` plus ruis; de fit moet
  `b` binnen 5% en `T_b` binnen 0,5 °C terugvinden; NAC-besparing van een kunstmatige
  isolatiestap binnen het bootstrap-interval.
- Referentiecase "Heerlen": echte KNMI-data station 380 plus geëxporteerde meterstanden
  (mindergas) uit vier gasjaren; `classic` moet mindergas.nl reproduceren binnen 1%.
