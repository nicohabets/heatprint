# Calculation methods (METHODS)

This document is the normative specification of all calculations in `heatprint_core`.
Code follows this document; deviations are recorded here first.

All daily values are per **local calendar day** of the site (site time zone).
Units: temperature in °C, wind speed in m/s, global radiation in J/cm² per day,
energy in kWh, gas in m³, heat (district heating) in GJ.

---

## 1. Constants and conversions

| Name | Value | Notes |
|---|---|---|
| `GAS_HS_KWH_PER_M3` | 8.792 | Higher heating value of Groningen-quality natural gas: 31.65 MJ/m³. Dutch suppliers bill on the higher heating value. |
| `GAS_HI_KWH_PER_M3` | 7.92 | Lower heating value (approx. 28.5 MJ/m³), only for users who want to calculate on the lower heating value. |
| `GJ_TO_KWH` | 277.78 | 1 GJ = 277.78 kWh. |
| `MJ_M2_TO_J_CM2` | 100 | 1 MJ/m² = 100 J/cm² (Open-Meteo daily sum to KNMI unit). |
| `WH_M2_TO_J_CM2` | 0.36 | 1 Wh/m² = 0.36 J/cm² (Open-Meteo hourly sum to KNMI unit). |
| `KMH_TO_MS` | 1/3.6 | Open-Meteo wind in km/h to m/s. |
| `KNMI_TENTHS` | 0.1 | KNMI `TG` (0.1 °C) and `FG` (0.1 m/s) are in tenths. `Q` is already in J/cm². |
| `GAS_CO2_KG_PER_M3` | 1.78 | Default emission factor for natural gas in NL (configurable). |
| `ELEC_CO2_KG_PER_KWH` | 0.30 | Default emission factor for electricity in NL (configurable, or live via a CO₂ sensor). |
| `W_PER_K_FROM_KWH_PER_K_DAY` | 1000/24 | kWh/(K·day) to W/K. |

---

## 2. Daily weather input

Every weather provider delivers a `DailyWeather`:

| Field | Type | KNMI source | Open-Meteo source | HA sensor source |
|---|---|---|---|---|
| `date` | date | `YYYYMMDD` | `time` | statistics period |
| `t_mean` | °C | `TG` × 0.1 | hourly mean of `temperature_2m` | daily mean of `mean` |
| `wind_mean` | m/s | `FG` × 0.1 | hourly mean of `wind_speed_10m` (km/h → m/s) | daily mean (unit from sensor) |
| `radiation` | J/cm² | `Q` | hourly sum of `shortwave_radiation` (Wh/m² × 0.36) or daily sum `shortwave_radiation_sum` (MJ/m² × 100) | daily sum/mean × 24 × 0.36 |
| `t_min`, `t_max` | °C | `TN`, `TX` × 0.1 | `temperature_2m_min/max` | `min`/`max` |
| `provisional` | bool | last 1-2 days | model instead of reanalysis (forecast API `past_days`) | incomplete day |
| `source` | str | `knmi:380` | `open_meteo:50.87,5.99` | `ha:sensor.x` |

A missing `wind_mean` or `radiation` may be `None`; methods that need them then fall back
to the temperature-only variant and set the flag `WEATHER_PARTIAL`.

---

## 3. Effective temperature (family)

All methods use one generic definition with a preset:

```
T_eff(d) = t_mean(d) - c_lin * wind_mean(d) - c_sqrt * sqrt(wind_mean(d)) + c_sun * radiation(d)
TAC(d)   = w_0 * T_eff(d) + w_1 * T_eff(d-1)          (inertia weighting, w_0 + w_1 = 1)
```

| Preset | `c_lin` | `c_sqrt` | `c_sun` | `w_0` / `w_1` | Origin |
|---|---|---|---|---|---|
| `none` | 0 | 0 | 0 | 1 / 0 | Plain daily mean temperature (mindergas, classic degree days). |
| `knmi` | 1/1.5 | 0 | 0 | 1 / 0 | KNMI/GTS "effective temperature" (T - wind/1.5), used for the gas-year degree days. |
| `pbl` | see note | see note | 1/480 (optional, off by default) | 0.65 / 0.35 | PBL 2022, KEV-SJV methodology: inertia 0.65/0.35, wind as the square root of the wind speed, sun as 1/480 of the daily radiation (only in the "optimal" model). |
| `house` | fitted | 0 | fitted (optional) | 0.65 / 0.35 (or fitted) | House-specific fit, see §7. |

**PBL wind term (verified against PBL 2022, eq. 17 and 20).** The daily KEV-SJV effective
temperature is

```
T_eff(d) = t_mean(d) - sqrt(wind_mean(d))  [+ radiation(d)/480 when include_sun]
TAC(d)   = 0.65 · T_eff(d) + 0.35 · T_eff(d-1)
```

so `c_sqrt = 1.0` (not the hourly Informatiecode term `sqrt(wind)/0.35`, which belongs to
the gas-profile methodology and is a different formula). Heatprint exposes both wind modes:

- `pbl_wind_mode = "linear"` (default, KNMI-style): `c_lin = 1/1.5`, `c_sqrt = 0`
- `pbl_wind_mode = "sqrt"` (authentic daily KEV-SJV): `c_lin = 0`, `c_sqrt = PBL_WIND_SQRT_COEF`
  (default `1.0`, configurable)

`include_sun` is **off by default** (the practical PBL model is temperature + wind only —
PDF eq. 20). When enabled, `c_sun = 1/480` (PBL 2022, "1/480ste van de zoninstraling")
and the generic `T_eff` family folds radiation into each day's `T_eff` *before* the
0.65 / 0.35 inertia:

```
T_eff,d = T_d − f_wind(W_d) + Q_d / 480
TAC     = 0.65 · T_eff,d + 0.35 · T_eff,d−1
```

PDF eq. 17 instead adds `Q/480` **outside** the inertia (today's radiation only).
Heatprint keeps the generic family (sun inside `T_eff`) because that is how this
document defines the four-method stack and because `include_sun` is off in the
default practical model. Enabling sun therefore also weights yesterday's
radiation — a documented deviation from eq. 17. With `include_sun` off and
`wind_mode = sqrt`, TAC matches PDF eq. 20 exactly.

The house-specific fit (§7) estimates the wind sensitivity itself and is therefore the recommended
method for a single house; the PBL preset is a nationally calibrated reference.

If day `d-1` is missing (first day of the series): use `TAC(d) = T_eff(d)` and set the flag `WEATHER_PARTIAL`.

---

## 4. Degree-day methods

Each method yields a number `dd[method]` ≥ 0 per day. All methods are always calculated and
stored; the user chooses which ones to display.

### 4.1 `classic` - classic (weighted) degree days, mindergas-compatible

```
if t_ref(d) < T_limit:  DD = max(0, T_base - t_ref(d))  else 0
WDD = DD * w_month
```

- `t_ref` = `t_mean` (default, mindergas-compatible) or `T_eff` of a chosen preset.
- `T_base` = 18.0 °C (mindergas: "average indoor temperature"), `T_limit` = 18.0 °C
  (mindergas: "heating limit"; users often choose 15.5 °C).
- Monthly factors `w_month` (mindergas weighting): Nov-Feb 1.1; Mar and Oct 1.0; Apr-Sep 0.8.
  Can be disabled (`weighted=false` gives unweighted degree days).

Goal: one-to-one comparable with mindergas.nl and with the HACS integration "Degree-days".

### 4.2 `knmi14` - KNMI gas-year degree days

```
DD = max(0, 14 - T_eff_knmi(d))
```

The gas year runs from 1 October through 30 September. Goal: align with the national
KNMI publications on "degree days in the gas year".

### 4.3 `pbl` - PBL 2022 / KEV-SJV (practical model)

```
DD = RER_m * max(0, TST_m - TAC_pbl(d))     [+ TOP_m if include_top]
```

Monthly parameters (PBL Table 3.4, practical model, De Bilt, temperature + wind, 1 day of history):

| Month | TST (°C) | RER | TOP |
|---|---|---|---|
| Dec, Jan, Feb | 17.01 | 1.00 | 1.30 |
| Mar, Nov | 15.26 | 1.02 | 1.30 |
| Apr, Oct | 15.10 | 0.79 | 1.30 |
| May through Sep | 13.92 | 0.61 | 1.30 |

Alternative parameter set `pbl_optimal` (Table 3.3, 6 stations + sun): TST 14.91 / 15.09 / 15.52 /
15.15; RER 1.00 / 0.96 / 0.82 / 0.73; TOP 1.32.

- `include_top` is **off** by default: TOP is the temperature-independent part (domestic hot water,
  cooking) and is handled separately in Heatprint (§6). TOP does not belong in the weather
  correction of space heating (PBL does the same: comparison without TOP for the sector application).
- The monthly parameters are national (profile category G1A, 2015-2020). For a single house they
  are indicative; see `house`.

### 4.4 `house` - house-specific degree days

```
DD = max(0, T_b - TAC_house(d))
```

`T_b` (balance temperature) and the wind sensitivity come from the energy signature fit (§7) of the
most recent heating season with sufficient data. `TAC_house` is **always** the house preset
(0.65/0.35 weighting, without wind term; the wind is in the fit as a separate regressor), so that
the basis of the fit does not change before and after fitting. As long as there is no fit, only the
degree-day value falls back: `DD = max(0, 15.5 - TAC_pbl)` with flag `HOUSE_NOT_FITTED`.

---

## 5. From energy carrier to heat

Per `Generator` (heat generator) per day:

| Kind (`kind`) | Input | Total heat `Q_total` | Electric `E_el` |
|---|---|---|---|
| `gas_boiler` | `V` m³ | `V * HV * eta` (HV = `GAS_HS_KWH_PER_M3` or Hi; `eta` default 0.95) | 0 |
| `heat_pump` | `E_th` kWh (thermal, measured) and/or `E_el` kWh | `E_th` if measured; otherwise `E_el * SCOP` (SCOP default 3.5; labelled "estimated") | `E_el` |
| `electric_heater` | `E_el` kWh | `E_el * 1.0` | `E_el` |
| `air_to_air` | `E_el` kWh | `E_el * COP` (COP default 3.0) | `E_el` |
| `district_heat` | `H` GJ (or kWh) | `H * 277.78 * eta` (eta default 1.0) | 0 |
| `other` | `x` | `x * factor` | 0 or `x` |

Rules:

- Cumulative meter readings are first converted to daily consumption (§9).
- If both `E_th` and `E_el` are measured for a heat pump: `COP_day = E_th / E_el`
  (only reported if `E_el > 0.2 kWh`).
- Heat pump with only `E_el`, and `air_to_air` (COP-estimated): `Q_total` gets the flag
  `HEAT_ESTIMATED`. Optionally (`cop_curve`): COP based on `t_mean`
  (`COP = max(1.0, cop_curve_a + cop_curve_b * t_mean)`, default a = 2.2 and b = 0.08).
  The floor of 1.0 keeps the estimate from dropping below a resistive heater on very
  cold days. Without `t_mean` the curve falls back to the configured SCOP.
- Hybrid = `gas_boiler` + `heat_pump` on the same site; nothing special in the conversion.

---

## 6. Domestic hot water and cooking split (DHW)

For each generator with `role = both`, `Q_total` is split into `Q_dhw` and `Q_space`:

| `dhw_mode` | Rule |
|---|---|
| `measured` | `Q_dhw` from a separate sensor (e.g. a heat pump reporting "DHW kWh"); `Q_space = Q_total - Q_dhw` (min 0). |
| `baseline` (default) | `B` = average daily consumption of the carrier over the **summer window** (default 1 June through 31 August of the last complete summer, at least 30 days). `Q_dhw = min(Q_total, B * conversion)`, `Q_space = Q_total - Q_dhw`. No summer available: lowest rolling 30-day average in the series. |
| `fixed` | Fixed value per day (in carrier unit or kWh), specified by the user (mindergas-style "monthly consumption for hot water and cooking" / 30). |
| `none` | Everything is space heating. |

`role = dhw`: `Q_space = 0`. `role = space`: `Q_dhw = 0`.
The baseline `B` is expressed in **carrier units** (m³/day, kWh/day, GJ/day; thermally measured
heat pumps: kWh_th/day) and is converted per day using the actual conversion of that day
(`Q_total / carrier`), which for fixed efficiencies equals `B * conversion`. If there is no
baseline (fewer than 30 summer or rolling days), all heat of that generator counts as space
heating and the day is flagged `DHW_BASELINE_MISSING` (informational; allowed in fits).
`measured` without a measurement on that day falls back to the same baseline (and the same
flag when the baseline is missing).
The baseline is calculated per generator and stored as `dhw_baseline_per_day` (sensor).
v2: monthly profile for the baseline (cold-water inlet temperature varies; summer ≈ 0.85 × winter).

---

## 7. Energy signature fit (PRISM-like)

Goal: per period (usually a heating season), fit the model

```
Q_space(d) = a + b * H(d) + c * wind_mean(d)        with H(d) = max(0, T_b - TAC(d))
```

by least squares, where `T_b` is determined by grid search.

Procedure:

1. Select the days in the period without exclusion flags (`ENERGY_MISSING`, `PARTIAL_DAY`,
   `WEATHER_MISSING`, `OUTLIER`). At least `n >= 30`, of which at least 15 with `H > 0`.
2. For `T_b` in `[6.0 ; 22.0]` with step 0.1: calculate `H(d)`, perform OLS (with or without `c`),
   store the SSE. Choose the `T_b` with the minimum SSE. `TAC` uses the `pbl` preset weighting (0.65/0.35)
   without wind term; the wind sensitivity is in `c` (option `fit_wind`, on by default).
3. Report: `T_b`, `a`, `b`, `c`, `r2`, `rmse = sqrt(SSE/n)`, `sse`, `n`,
   `n_heating_days`, `outliers`, `UA = b * 1000/24` (W/K), `ci95_b = b ± t(n-p) * SE(b)`
   (p = number of parameters: 2 without, 3 with wind term), `ci95_Tb` from the profile
   (all `T_b` for which `SSE <= SSE_min * (1 + F_0.95(1, n-p)/(n-p))`).
4. Outliers: after the first fit, mark days with `|residual| > 4 * rmse` as `OUTLIER` and
   refit once.

Interpretation in the UI:

- `b` (kWh per K per day) and `UA` (W/K): heat loss of the house. Decreases with insulation.
- `T_b`: balance temperature. Decreases with a lower thermostat setting, more internal heat gains,
  better use of solar gains. Increases with higher setpoints.
- `a`: temperature-independent remainder (should be ≈ 0 if the DHW split is correct).

---

## 8. Normalized consumption, comparison and forecast

### 8.1 Climatology

`TAC_clim(doy)` = mean `TAC` per day of year over the reference years
(default the last 20 years, which KNMI has; Open-Meteo from 1940 onwards). Also `dd_clim[method](doy)`
and `wind_clim(doy)`. Calendar with 366 slots (leap year); slot 60 bundles 28/29 February and
1 March so that every year fills the same slots. Stored per site (with `tac_preset` and the number of
samples per slot) and refreshed annually.

### 8.2 Normalized seasonal consumption (NAC)

For a fit `(a, b, c, T_b)` over a season window:

```
NAC = Σ_doy [ a + b * max(0, T_b - TAC_clim(doy)) + c * wind_clim(doy) ]
```

Saving between fit 1 (before) and fit 2 (after): `S = (NAC_1 - NAC_2) / NAC_1`.
Confidence interval: bootstrap (200 resamples of days, fixed seed 42) on both fits;
each resample refits on a **0.5 K** balance-temperature grid (no outlier pass) and
the 2.5% and 97.5% percentiles of `S` are reported. The coarser grid is a speed
trade-off against the 0.1 K grid of the published fit.

### 8.3 Simple period comparison (mindergas-style)

```
k_i = Q_space(period_i) / Σ dd[method](period_i)
Δ% = (k_2 - k_1) / k_1
```

Requirements: both periods ≥ 30 days and Σ dd ≥ 100 (classic) or ≥ 50 (other methods).
`min_dd` can be lowered (including to 0) but Σ dd must still be **> 0**: `k = Q / Σ dd`
is undefined otherwise, and the core raises `InsufficientDataError` rather than returning
NaN. With too little data the core raises an `InsufficientDataError` (no partial
`Comparison`). Available for every method so that the user can see how the choice of
method affects the result.

### 8.4 Measure effect

A `Measure` has a date. Comparison = season(s) before vs. season(s) after, using
§8.2 (primary) and §8.3 (secondary). Overlapping measures within one season are
reported jointly (they cannot be separated; the UI says so explicitly).

### 8.5 Forecast for the current season

```
DD_rest             = Σ dd_clim[method](doy) over the remaining season days
Q_space_forecast    = Q_space_ytd + k_ytd * DD_rest
Q_dhw_forecast      = Q_dhw_ytd + Q_dhw_per_day * days_remaining
Q_forecast          = Q_space_forecast + Q_dhw_forecast
```

with `k_ytd = Q_space_ytd / Σ dd_ytd`. Space heating and domestic hot water are forecast and
reported separately. If there is a valid fit, a second variant `Q_space_forecast_fit` uses the
§8.2 model over `TAC_clim`. Per carrier: `Q_forecast` distributed according to the share of the last 28
days (hybrid: gas m³ and heat pump kWh separately). Also report `method`, `k_ytd` and `days_remaining`.

---

## 9. Meter readings to daily consumption

Input: series of `(timestamp, cumulative reading)` (HA long-term statistics `sum`/`state`, or
CSV import). Output: consumption per local day.

1. Sort, remove duplicates, detect resets (`reading decreases`): start a new series.
   The day of the reset gets the sum of the measured parts before and after the reset and the flag
   `METER_RESET`; days that fall entirely within a gap around the reset are missing.
2. Linearly interpolate the reading at every day boundary (00:00 local).
3. Daily consumption = reading(d+1 00:00) - reading(d 00:00).
4. Gap between two readings > 3 days: all days within it get `INTERPOLATED`.
5. First/last day with incomplete coverage: `PARTIAL_DAY`.

---

## 10. Data quality flags

| Flag | Meaning | Effect |
|---|---|---|
| `WEATHER_MISSING` | no weather data | excluded from fit and k calculation |
| `WEATHER_PARTIAL` | wind/sun/d-1 missing | method falls back; allowed in fit |
| `WEATHER_PROVISIONAL` | provisional weather data | overwritten later |
| `ENERGY_MISSING` | no generator has any data, or a generator is missing data within its own date range (so a heat pump installed later does not invalidate the gas history) | excluded |
| `PARTIAL_DAY` | incomplete coverage | excluded |
| `INTERPOLATED` | consumption from long interpolation | allowed, weight 1 (v2: lower weight) |
| `METER_RESET` | meter reset | excluded |
| `HEAT_ESTIMATED` | heat pump heat via SCOP | allowed, labelled |
| `HOUSE_NOT_FITTED` | no house fit | `house` = fallback |
| `OUTLIER` | residual > 4 × rmse | excluded after refit |
| `IMPORTED` | from CSV | informational |
| `DHW_BASELINE_MISSING` | no DHW baseline (and no measurement that day) | all heat of that generator as space heating; allowed in fits |
| `PRICE_ESTIMATED_FLAT` | dynamic tariff lacked hourly statistics that day | day's mean price × billed amount; allowed |

---

## 11. Validation (definition of done for the calculation core)

- Unit tests per formula with manually verified examples (including KNMI tenths,
  mindergas weighting, PBL monthly parameters, DHW baseline, meter interpolation, reset).
- Synthetic house: generate 2 seasons with known `(a, b, T_b)` plus noise; the fit must
  recover `b` within 5% and `T_b` within 0.5 °C; the NAC saving of an artificial
  insulation step must lie within the bootstrap interval.
- Reference case "Heerlen": real KNMI data from station 380 plus exported meter readings
  (mindergas) from four gas years; `classic` must reproduce mindergas.nl within 1%.
  The live export is a v0.2 item (needs Nico's files). Pre-alpha tests reproduce the
  mindergas *formula* on fixture weather within 1%.

---

## 12. Per-room heat allocation and heat loss (rooms)

Goal: split the site's daily `heat_space_kwh` (§5-6) across rooms, and estimate an apparent
per-room heat loss and balance temperature, using whatever room-level heating-demand signal
the user's thermostat integration exposes (Tado/`tado_ce`, Zigbee TRVs, and others - §12.6).
This is an **allocation and estimate**, not a substitute for a design heat-loss calculation
(such as EN 12831): rooms exchange heat with each other and with unheated spaces, so the
apparent per-room UA below includes that exchange and is systematically different from an
isolated-room figure. §12.9 states this explicitly wherever a per-room number is shown.

### 12.1 Room demand signal and daily demand integral

A `Room` (§DATA_MODEL §1.6) is optionally linked to one **demand entity** of one **kind**:

| `demand_kind` | Example source | Native range | Daily integral `D_r(d)` |
|---|---|---|---|
| `percentage` | Tado zone heating-power sensor (`sensor.<room>_verwarming`, `%`, `state_class measurement`) | 0-100 | mean(%) × 24 h → `%·h`, then ÷ 2400 to a 0-1 fraction of a fully-heated day |
| `valve_position` | Zigbee/Z-Wave TRV valve-opening or demand attribute exposed as a sensor | 0-100 | same as `percentage` |
| `binary` | `climate.<room>` `hvac_action` (`heating`/`idle`), or a pump/relay switch | on/off | fraction of the day in the "on" state (hours ÷ 24) |
| `metered_energy` | A dedicated electric emitter on a metered plug/circuit (e.g. an electric floor-heating plug) | kWh/day | not integrated - the kWh *is* `heat_room_kwh` directly (§12.3) |

For `percentage`/`valve_position`/`binary`, `D_r(d)` is read preferentially from **long-term
statistics** (`mean` × hours, matching how Heatprint already reads HA-sensor weather inputs,
§2) when the entity has `state_class: measurement`; if it does not, or no statistics exist yet
for the requested date, the recorder's raw history (~10 days) is used instead and the day gets
flag `ROOM_DEMAND_FROM_HISTORY`. Days before the entity had recorded data get `ROOM_DEMAND_MISSING`
and are excluded from allocation and from the room's fit (§12.4). This means a room's history
starts wherever the demand entity's statistics start - **it cannot be backfilled** the way KNMI
weather can (§DATA_MODEL notes the same limit for HA-sensor weather sources).

### 12.2 Room weight

To turn a relative demand signal into a share of the site's total heat, each room with an
`emitter_kind` other than `metered_energy` gets a weight `w_r` approximating its emitter's
rated output:

```
w_r = rated_output_w                                    (if the user supplies it)
w_r = floor_area_m2 * DEFAULT_OUTPUT_W_PER_M2[emitter_kind]   (otherwise)
w_r = 1                                                  (if neither is set - flag ROOM_WEIGHT_ASSUMED)
```

`DEFAULT_OUTPUT_W_PER_M2` is a small configurable table keyed by `emitter_kind`
(`radiator`, `underfloor`, `electric`, `other`), seeded with indicative Dutch-housing figures.
**These defaults are placeholders**, in the same spirit as the PBL wind coefficient in §3: until
verified against a published source they are configurable and every room using them is flagged
`ROOM_WEIGHT_ASSUMED` so the UI can say plainly "this room's share is an estimate." See the
ROADMAP research item "default emitter output per m²".

A more detailed emitter law (rated output scaling with the flow/room temperature difference,
as radiator output is known to do non-linearly) is **not** modelled in v1: the demand signal
already reflects the thermostat's own modulation, and adding a second, unverified non-linear
correction on top would create false precision. This is a documented simplification, not an
oversight - revisit if a validated coefficient set becomes available.

### 12.3 Allocation

For each day `d`, before allocating, subtract every room's directly metered heat:

```
heat_metered(d)   = Σ_{r: metered_energy} heat_room_kwh_r(d)
heat_to_allocate(d) = max(0, heat_space_kwh(d) - heat_metered(d))
```

Then, over the remaining rooms (those with a `percentage`/`valve_position`/`binary` demand
entity and `D_r(d)` available that day):

```
share_r(d)      = w_r * D_r(d) / Σ_r' w_r' * D_r'(d)
heat_room_kwh_r(d) = share_r(d) * heat_to_allocate(d)      (r not metered_energy)
```

Rooms without any demand entity, or without `D_r(d)` for that day, get no allocation for that
day. What is left over -

```
heat_unallocated_kwh(d) = heat_to_allocate(d) - Σ_{r allocated} heat_room_kwh_r(d)
```

- is stored as a site-level series (`heatprint:<site>_heat_unallocated`, §DATA_MODEL §2.2) so the
per-room breakdown is always reconcilable against the site total: it covers rooms without a
configured room, distribution losses, and any day where every configured room lacked data.

### 12.4 Per-room heat loss (room energy signature)

Primary method, reusing the site-level fit machinery of §7 per room instead of per site:

```
heat_room_kwh_r(d) = a_r + b_r * max(0, T_b,r - TAC(d)) [+ c_r * wind_mean(d)]
```

Same procedure as §7 (grid search over `T_b,r`, OLS, outlier refit, `n >= 30` with at least 15
heating days, `UA_r = b_r * 1000/24` in W/K, `r2`, `rmse`, `ci95_slope`, `ci95_balance`). Uses
site TAC (not a room-specific effective temperature - a single house has one outdoor climate).
Days with `ROOM_DEMAND_MISSING` for that room are excluded, same as `ENERGY_MISSING` at site
level. Before a room has 30 qualifying days, `sensor.<site>_room_<room>_heat_loss_coefficient`
is unavailable and the room carries flag `ROOM_NOT_FITTED`.

Secondary, indicative-only cross-check (available immediately, before 30 days of data exist):

```
UA_r_indicative = heat_room_kwh_r(heating hours, kWh) / (T_room_mean - t_mean) / heating_hours * 1000
```

computed only over hours where the room's demand signal is non-zero and a room temperature
reading is available (`temperature_entity`, optional per room - most thermostat integrations,
including Tado, already report current room temperature on the `climate` entity, but that value
is a live attribute, not itself in long-term statistics; Heatprint reads it the same way it
reads a `binary` demand signal, via history/statistics on a dedicated temperature entity if one
is configured, falling back to the `climate` entity's own recorded state changes otherwise).
This indicative estimate is shown labelled as such and is **not** used for cost or for the
season total; it exists only so a new install shows *something* before a season's worth of
data has accumulated for the regression.

A third method - identifying the room's thermal time constant from its temperature decay while
unheated (RC identification) - is a plausible v2 refinement and is listed as a roadmap research
item rather than specified here; it needs validation against Heatprint's synthetic-house
approach (§12.8) before being trusted.

Per-m² normalization: `UA_r` (W/K) is not comparable between a large living room and a small
toilet, or between rooms in different houses. Where `floor_area_m2` is set, Heatprint also
reports the **specific heat loss** `ua_w_per_k_per_m2 = UA_r / floor_area_m2` (W/(m²·K)) -
this is the figure that is actually comparable room-to-room and, later, house-to-house - the same unit PRODUCT_BRIEF §6.4
already names for its v2.0 anonymous benchmark idea ('W/K per m² and year of construction'). `floor_area_m2` also normalizes cost and heat
(`heat_kwh_per_m2_season`, `cost_eur_per_m2_season`), which is the more familiar unit for most
people (it is how Dutch EPC/energy-label figures, kWh/m²/year, are usually expressed) even
though it is not itself directly used in the allocation of §12.3.

`volume_m3` (optional; defaults to `floor_area_m2 * DEFAULT_CEILING_HEIGHT_M` if only the area
is given) is captured on the `Room` config now but **not used by any calculation in this
version**. It is reserved for a future refinement where it would matter physically:
ventilation/infiltration heat loss scales with air volume, not floor area, and the RC
thermal-mass cross-check mentioned above needs a volume to convert its time constant into a
heat capacity. Capturing it now avoids a breaking config migration later; it does nothing on
its own until that method exists.

### 12.5 Per-room and total cost

`cost_eur` is computed per site per day from each generator's `price_entity` (§DATA_MODEL
§2.1) and written as `heatprint:<site>_cost` (0.2.4). Room cost follows the same allocation as heat:

```
cost_space_eur(d) = Σ_generators cost_eur(d) restricted to that generator's space-heating share
cost_room_eur_r(d) = share_r(d) * cost_space_eur(d)              (r not metered_energy)
cost_room_eur_r(d) = heat_room_kwh_r(d) * price(d)                (r metered_energy, its own price_entity or the site default)
```

DHW cost is excluded (rooms only cover space heating). Fixed standing charges (gas connection
fee, standing charge on a supply contract) are **out of scope**, consistent with §6.5 of
PRODUCT_BRIEF ("no billing/energy supplier integrations") - Heatprint estimates relative usage
cost, not a bill. For a hybrid site, a day's `cost_space_eur` already blends both carriers'
prices at the site level (via each generator's own `cost_eur`); room allocation does not need to
know which carrier heated which room. Season and total-to-date sums follow the existing pattern
(`sensor.<site>_room_<room>_cost_season`, §DATA_MODEL §4).

This is the direct answer to "which room is costing me the most": once `cost_room_eur` accumulates
for a season, ranking rooms by it - or by `heat_room_kwh` for a carrier-neutral view, or by
`UA_r` (§12.4) for "which room loses heat fastest regardless of how much it was actually
heated" - needs no extra calculation, only a sort. §DATA_MODEL §4 adds a small ranking sensor
so a dashboard does not have to build that sort itself.

### 12.6 Demand-signal sources (non-exhaustive)

Verified on Nico's own instance (HA core 2026.9.2, `tado_ce` by hiall-fyi, 18 zones each a
distinct HA area with one `climate.<room>` entity): every zone has a heating-power sensor
`sensor.<room>_<room>_verwarming` (`%`, `state_class: measurement`) - this is the primary
`percentage` source and is already recorded to long-term statistics going forward. The same hub
also exposes a boiler flow/output temperature (`°C`, `state_class: measurement`) that is useful
context but is not itself a per-room signal. Four of Nico's zones report `no_heating_circuit` on
`select.<room>_heating_circuit` (Keldertrap, Overloop, Sauna, Toilet) - rooms on those zones may
have a Tado presence without an active radiator circuit and should default to no room configured
rather than a guessed weight. Two underfloor-heating pump automations exist for Woonkamer and
Serre (their exact trigger logic was not inspected for this design) confirming at least those two
rooms use `emitter_kind: underfloor`, not `radiator`; smart plugs feeding electric floor heating
in the Garage and Wasruimte areas are a likely `metered_energy` room and should be checked
during implementation for their actual energy-sensor entity id.

Other integrations that plausibly expose a compatible `percentage`/`valve_position`/`binary`
signal and should map onto the same abstraction (unverified specifics - confirm entity/attribute
names against each integration's current docs before implementing that adapter): the core `tado`
integration's own heating-power sensor; Zigbee TRVs via Zigbee2MQTT or ZHA that expose a valve
position or PI heating-demand percentage; Homematic IP and Plugwise climate valve-position
sensors; any `climate` entity's `hvac_action` as a last-resort `binary` fallback when nothing
finer-grained is available. Heatprint should treat this as an open, per-integration adapter list
rather than hard-coding Tado - see ROADMAP for the research item to build that matrix.

### 12.7 Data quality flags (rooms)

| Flag | Meaning | Effect |
|---|---|---|
| `ROOM_DEMAND_MISSING` | no demand-entity data for that room on that day | excluded from allocation and fit |
| `ROOM_DEMAND_FROM_HISTORY` | demand integral read from raw history, not statistics | allowed, informational |
| `ROOM_WEIGHT_ASSUMED` | no `rated_output_w`/`floor_area_m2`, weight defaulted to 1 | allowed, labelled |
| `ROOM_NOT_FITTED` | fewer than 30 qualifying days | `heat_loss_coefficient` unavailable; indicative estimate (§12.4) shown instead |
| `ROOM_TEMPERATURE_MISSING` | no room temperature available | indicative UA estimate unavailable |

### 12.8 Validation

Synthetic multi-room house: generate a site with `N` rooms of known `(UA_r, T_b,r)`, a known
site-level `heat_space_kwh(d)` consistent with `Σ UA_r`, and a controller that turns each room's
synthetic demand signal roughly proportional to that room's own instantaneous deficit
(`T_b,r - TAC(d)`) plus noise. The room fit (§12.4) must recover each `UA_r` within a **looser**
tolerance than the site-level fit's 5% (proposed: 20%, since the demand signal is a noisier proxy
than a direct meter) and the allocated shares must sum to the known input shares within a stated
tolerance. This bound is a starting proposal, to be tightened once real multi-season data exists.

### 12.9 Interpretation and honesty (extends §9 of PRODUCT_BRIEF)

Every room-level number shown in the UI carries the caveat that it is an **apparent** figure: a
room's fitted UA includes heat exchanged with neighbouring rooms and with unheated spaces (attic,
crawl space), not just the losses through its own external envelope, and depends on how well the
demand signal tracks actual delivered heat (a thermostat's percentage output is a control-loop
output, not a calibrated flow measurement). Rooms are for **relative comparison within one house**
(which room loses more, which room got cheaper after a measure) - they are not a substitute for
an EN 12831-style design heat-loss calculation and Heatprint does not claim that precision.

---

## 13. Cost and CO₂

`DailyRecord.cost_eur` and `.co2_kg` are named in §DATA_MODEL §2.1. This section specifies how
they are computed (flat and dynamic) and how the Home Assistant layer writes them as statistics
and sensors (0.2.4).

### 13.1 Flat tariff (default)

Per generator with a `price_entity` set:

```
cost_eur(d)  = Σ_generators carrier_amount(d) * price(d)
co2_kg(d)    = Σ_generators carrier_amount(d) * co2_factor
```

`price(d)` is the day's reading of `price_entity` (a slowly-changing €/unit sensor - a fixed
contract rate, or a manually-updated one). `co2_factor` is per generator (§DATA_MODEL §1.3),
default per kind (§1 constants), or overridden by a live CO₂-intensity sensor if one is
configured. This is unchanged from the (previously unwritten) existing behaviour implied by
`DailyRecord.cost_eur`/`.co2_kg` and by F18.

### 13.2 Dynamic/day-ahead tariff (`price_mode: dynamic`)

Available per generator, and only meaningful for an **electric** carrier (`heat_pump` via
`carrier.electric_entity`, `electric_heater`, `air_to_air` - not `gas_boiler` or `district_heat`,
which have no equivalent liquid hourly retail market in NL today). In the Netherlands, day-ahead
electricity prices (Nordpool-based, exposed by several HA integrations) commonly range from
negative to well over €0.40/kWh within one day, so a heat pump's hourly load profile relative to
price volatility matters far more than for a flat tariff - a single daily price average hides
that entirely.

```
cost_eur_generator(d) = Σ_h∈hours(d) electric_kwh(d,h) * price(d,h)
```

`hours(d)` is the site's local calendar day, 23/24/25 hours on a DST-transition day (same day
definition as everywhere else in this document). Both series are read the same way Heatprint
already reads any HA-sensor input - from the entity's own **recorded hourly statistics**
(`recorder_source.py`'s existing `statistics_during_period`, extended to hourly instead of daily
resolution for this calculation only):

- `electric_kwh(d,h)`: hourly `sum`/`change` of the generator's `carrier.electric_entity` -
  requires that entity to have `state_class: total_increasing`, already a requirement for any
  `carrier.energy_entity` (§DATA_MODEL §1.3).
- `price(d,h)`: hourly `mean` of `price_entity` - requires the price entity itself to have
  `state_class: measurement` and hourly statistics, which is how HA dynamic-price integrations
  commonly expose their **current/historical** price (their *forecast* attributes for
  today/tomorrow are a separate, integration-specific shape that this calculation deliberately
  does not depend on - see ADR 0006).

If either series lacks hourly statistics for a day (heat pump with only a `cop_fixed`/SCOP
estimate and no separate electric meter; a price entity without statistics that day), that
generator's cost for that day falls back to §13.1 using the day's mean price, flagged
`PRICE_ESTIMATED_FLAT`.

A season-to-date `sensor.<site>_<generator>_avg_price_paid` (€/kWh, `Σ cost_eur / Σ electric_kwh`)
reports the *actual* weighted-average price paid, which - unlike a simple daily mean - reflects
whether the generator's own load pattern outperformed or underperformed the day's average price.

Per-room cost allocation (§12.5) is unaffected: it multiplies `share_r(d)` by whatever
`cost_space_eur(d)` §13.1/§13.2 produced that day, flat or dynamic, without needing to know which.

### 13.3 CO₂

CO₂ stays daily-factor-based (§13.1). Site pricing options override the kind default when the
generator still has that default. A configured `co2_entity` (daily `mean` kg/kWh) overrides
electric generators on days it has a reading; missing days fall back to the generator factor.
Hourly grid carbon intensity is out of scope.

---

## 14. Data-source health checks

Beyond `binary_sensor.<site>_data_gap` (missing data for >3 days, already specified), Heatprint
should also catch data that *is* arriving but is wrong - a much more common failure mode in
practice than a sensor going fully silent. Run once per day, in the same pass as the daily
pipeline, over every configured generator, room demand entity and weather source:

| Check | Trigger | Distinct from |
|---|---|---|
| `STUCK_VALUE` | A cumulative meter has not changed for ≥ 3 days while the site otherwise shows heating activity (any generator's `heat_space_kwh > 0`) | `data_gap`, which is about *no data*, not an unchanging value |
| `IMPLAUSIBLE_VALUE` | A day's derived value (heat, degree days, room demand) is more than a configurable multiple (default 5×) of that series' own trailing 30-day robust typical value (median, not mean, to resist the outliers it is trying to catch) | `OUTLIER` (§10), which silently excludes a day from a *fit*; this check surfaces the same kind of anomaly to the user immediately, on the day it happens, independent of whether a fit is even running |
| `SCALE_DRIFT` | A sustained order-of-magnitude step change in an otherwise stable series (e.g. an integration update changes a sensor's unit or precision) that does not correspond to any known configuration change | A one-off `IMPLAUSIBLE_VALUE` (transient); this is a persistent shift, checked by comparing two trailing windows (e.g. days 1-15 vs. 16-30) rather than a single day against history |
| `WEATHER_STALLED` | `WEATHER_PROVISIONAL` (§2) has been set for longer than the provider's normal provisional window (1-2 days for KNMI) | routine provisional-data lag, which is expected and not a fault |

Each check that fires opens (and each day it no longer fires, closes) one HA repair
(`homeassistant.helpers.issue_registry`), naming the specific generator/room/weather source and
which check failed, with a short "what to check" hint (e.g. `STUCK_VALUE` on a gas meter →
"confirm the meter integration is still polling"). `sensor.<site>_data_quality` (§DATA_MODEL §4)
gains an attribute listing any currently-open checks, alongside its existing usable-days
percentage - so a user is not left reading a 90% "data quality" number without being told *why*
the other 10% failed.

These checks are deliberately simple threshold rules, not a statistical anomaly-detection model -
consistent with the core's "no numpy" constraint (ADR 0002) and with keeping every rule
explainable in one sentence, per §9 of PRODUCT_BRIEF.
