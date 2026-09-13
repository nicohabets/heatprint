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
