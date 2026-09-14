# Config flow (CONFIG_FLOW)

Goal: a user with gas, a heat pump, a hybrid system, all-electric heating or district heating
sets up Heatprint **within five minutes** without YAML, and can change everything later
without reinstalling.

Structure in Home Assistant (2026.9+):

- **Config entry** = one site (dwelling). Multiple sites are possible (second home).
- **Subentries** of type `generator` (heat generator) and `measure` (energy-saving measure).
- **Options flow** for methods, DHW defaults, backfill and integrations (mindergas bridge).
- **Reconfigure flow** for location and weather source.

```mermaid
flowchart TD
    A([Add integration]) --> B[Confirm HA home<br/>name/location/tz/country from HA<br/>weather + rooms + meters auto]
    B --> M([Entry created<br/>+ generator/room subentries])
    M --> N[Background: weather backfill,<br/>climatology, first calculation<br/>rooms dashboard]

    subgraph Later
        O[Subentry: add/edit generator]
        P[Subentry: add measure]
        U[Subentry: add room]
        Q[Options: methods, DHW, backfill,<br/>CSV import wizard, mindergas, prices/CO2, rooms]
        R[Reconfigure: location, weather source]
        V[Lovelace dashboard auto-created]
        S[Action: import_readings for automations]
    end
    M -.-> O
    M -.-> P
    M -.-> U
    M -.-> Q
    M -.-> R
    M -.-> S
    M -.-> V
```

---

## Step 1 - Confirm this Home Assistant home

First-run is **one confirm screen** with no extra fields. Heatprint reuses what
Home Assistant already has and does not ask the user to recreate a home:

| Value | Source | Notes |
|---|---|---|
| `name` | `zone.home` friendly name, else `hass.config.location_name`, else "Home" | unique per installation |
| `location` | HA home lat/lon (or `zone.home`) | never asked |
| `timezone` | HA time zone | never asked |
| `country` | HA country, else tz/coords | never asked; NL → nearest KNMI station |
| weather | KNMI nearest (NL) or Open-Meteo | Reconfigure to change; first-run does **not** block if the weather check fails (logged warning) |
| generators | gas / heat-pump energy sensors already in HA | **auto-created** when high-confidence sensors exist; add later if none |
| rooms | heated HA areas (see below) | auto-synced as `room` subentries |

Reconfigure remains the escape hatch for a second home or a different weather
station. Methods, DHW and history use the documented defaults (options).

Errors: `already_configured`.

**First-run stops after this confirm.** Weather, methods, DHW and history are
**not** asked here. The numbered steps below describe later surfaces
(Reconfigure, generator/measure/room subentries, Options). A leftover
sequential wizard (`situation` → generators → DHW → methods → history →
summary) still exists in `config_flow.py` but is **not** reached from
`async_step_user`.

After setup a **stock Lovelace dashboard** is created and shown in the sidebar
(`heatprint-<site_id>`). Entity cards look up current `entity_id`s by
`unique_id` (so a Dutch or other non-English UI does not get "Entity not
found"). Statistic ids stay `heatprint:<site>_<metric>`. Only built-in cards
(no apexcharts). Recreate with the action `heatprint.create_dashboard`.

## Later - Weather source (NL) — Reconfigure only

| Field | Selector | Default | Notes |
|---|---|---|---|
| `provider` | select: `knmi`, `open_meteo`, `ha_sensors` | `knmi` | |
| `station_id` | select (list with name + distance) | nearest KNMI station | list of ~35 stations with lat/lon in `const.py` |
| `fallback` | select: `open_meteo`, `none` | `open_meteo` | |

Validation: KNMI test request (last 7 days). Errors: `cannot_connect`, `no_data_for_station`.

## Later - Weather source (outside NL) — Reconfigure only

| Field | Selector | Default |
|---|---|---|
| `provider` | select: `open_meteo`, `ha_sensors` | `open_meteo` |
| `ha_entities.temperature` | entity (sensor, device_class temperature) | - |
| `ha_entities.wind` | entity (sensor, wind_speed) | optional |
| `ha_entities.radiation` | entity (sensor, irradiance) | optional |

Validation: Open-Meteo test request; with `ha_sensors`, a check for `state_class measurement`
(otherwise there are no long-term statistics → error `entity_no_statistics`).

## Heating setup (first-run auto-detect)

First-run **creates** generator subentries for every matching sensor (not
suggestions). Heat pumps get role `both` (not the leftover hybrid draft of
`space`). If none are found, add them later via the `generator` subentry.

| Detected sensor | Created generator |
|---|---|
| `device_class: gas` + `state_class: total_increasing` | `gas_boiler` (role `both`) |
| `device_class: energy` and a name containing warmtepomp / heat pump / hp / wp | `heat_pump` (role `both`, `electric_entity`) |

A leftover situation choice (`gas` / `hybrid` / `all_electric` / `district_heat` /
`custom`) still exists in `async_step_situation` and would prefill drafts
(`hybrid` → heat pump role `space`). It is **not wired** from first-run.

## Later - Generator (subentry `generator`)

Sub-steps depending on `kind`:

### 4.1 Kind and role

| Field | Selector | Default |
|---|---|---|
| `name` | text | per kind |
| `kind` | select | from step 3 |
| `role` | select: `space`, `dhw`, `both` | per kind |

### 4.2 Sensors

| `kind` | Required | Optional |
|---|---|---|
| `gas_boiler` | `energy_entity` (m³, total_increasing) | `dhw_entity` (rare) |
| `heat_pump` | at least one of `thermal_entity` (kWh_th) or `electric_entity` (kWh) | both; `dhw_entity` (kWh_th DHW), `dhw_electric_entity` |
| `electric_heater` | `energy_entity` (kWh) | |
| `air_to_air` | `energy_entity` (kWh) | |
| `district_heat` | `energy_entity` (GJ or kWh) | `dhw_entity` |
| `other` | `energy_entity` | |

Validation: the entity exists, `state_class` is `total` or `total_increasing`, the unit matches
the kind (m³ → gas; kWh/Wh/MWh → electric/thermal; GJ/MJ/kWh → district heating). Errors:
`entity_not_found`, `entity_not_cumulative`, `unit_mismatch`, `missing_thermal_or_electric`.

### 4.3 Conversion

| `kind` | Fields | Default |
|---|---|---|
| `gas_boiler` | `heating_value` (select Hs 8.792 / Hi 7.92 / custom), `efficiency` (0.5-1.1) | Hs, 0.95 |
| `heat_pump` | `mode` (auto: `measured_thermal` when a thermal sensor is present, otherwise `cop_fixed`), `scop` (1-7) | 3.5 |
| `air_to_air` | `cop` | 3.0 |
| `electric_heater` | - | factor 1.0 |
| `district_heat` | `efficiency` | 1.0 |
| `other` | `factor` | 1.0 |

Help text for `cop_fixed`: "Without a thermal meter the heat is an estimate;
Heatprint labels it as 'estimated'."

### 4.4 DHW/cooking (only with role `both`)

| Field | Selector | Default |
|---|---|---|
| `dhw_mode` | select: `baseline`, `fixed`, `measured`, `none` | `measured` when `dhw_entity` is set, otherwise `baseline` |
| `fixed_per_day` | number (carrier unit/day) | - |

The summer window for the baseline (`summer_window`, MM-DD, default 06-01 to 08-31) is a
site setting (step 5 and options), not a per-generator one.

### 4.5 Price and CO₂ (optional, collapsible)

| Field | Selector | Default |
|---|---|---|
| `price_entity` | entity (sensor) | - |
| `co2_factor` | number | per kind (gas 1.78 kg/m³; electricity 0.30 kg/kWh or a CO₂ sensor) |

After 4.5: "Add another generator?" (yes → 4.1).

## Later - DHW and cooking (site level, Options)

Only a summary and an optional override of the default from 4.4; plus an explanation of why
the split matters for the heating line.

## Later - Methods and season (Options)

| Field | Selector | Default |
|---|---|---|
| `season_start` | select: `1 October` (gas year), `1 January`, `1 July` | 1 October |
| `methods.enabled` | multi-select: `classic`, `knmi14`, `pbl`, `house` | classic, pbl, house |
| `methods.primary` | select | `house` |
| `classic.weighted` | boolean | true |
| `classic.base_temp`, `classic.heating_limit` | number | 18.0 / 18.0 |
| `pbl.parameter_set` | select: `practical`, `optimal` | practical |
| `pbl.wind_mode` | select: `linear`, `sqrt` | linear |
| `pbl.include_sun` | boolean | false (only when radiation is available) |
| `house.fit_wind` | boolean | true |

Advanced fields live under "Advanced" (collapsed section).

## Later - History (Options)

| Field | Selector | Default |
|---|---|---|
| `backfill_years` | number 0-10 | 3 |
| `climatology_years` | number 10-30 | 20 |
| `import_now` | boolean | false in stored defaults; **no Options control** (leftover field on the unused history wizard step). Use **Import meter readings** instead. |

Text: "Weather history is fetched in the background. Meter readings from before your Home
Assistant history can be imported from Configure → Import meter readings (CSV paste or
file; a mindergas.nl export needs no extra questions)."

## After confirm

Entry + generator/room subentries are created immediately. The coordinator starts
the weather backfill as a **persistent notification** (not a repair) in 90-day
chunks. Recreate the stock Lovelace overview and Rooms dashboards with
`heatprint.create_dashboard`.

---

## Subentry flows

### `generator` (add / edit / remove)

Same steps as 4.1-4.5. Changing `energy_entity` triggers a recomputation from the earliest
available date of the new sensor. Removing: the statistics of that generator are kept
(history) but are no longer updated. Home Assistant has no removal flow for subentries with
questions of its own, so "also clear statistics" is a separate service
(`heatprint.clear_statistics`) instead of a checkbox.

### `measure` (add / edit / remove)

| Field | Selector |
|---|---|
| `name` | text |
| `date` | date |
| `category` | select: `insulation`, `installation`, `behaviour`, `other` |
| `notes` | text (multiline) |

After creation the service `heatprint.measure_effect` can be called (only meaningful
once there are ≥ 30 days after the date). A dedicated "Compute effect" button after
the subentry is created is a v1.0 UI polish; the service is already wired.

### `room` (add / edit / remove)

**Usually created automatically** from Home Assistant areas on first setup, on
reload when auto-sync is on, or via **Configure → Sync rooms from HA areas**.
A manual add is only needed for a skipped area or a custom demand entity.

Discovery heuristics (METHODS §12.6):

1. Skip areas on the exclude list (options).
2. Skip areas with a Tado-style `select.*heating_circuit` (or climate attribute)
   whose state is `no_heating_circuit`.
3. Skip areas with no `climate` entity and no heating-demand / valve sensor.
4. Demand entity, in order: percentage heating-power sensor in the area (Tado
   `*_verwarming`, `heating_power`, `pi_heating_demand`); else a valve-position
   sensor; else the area's `climate` entity as `binary` demand from `hvac_action`.
5. Temperature: the area's `climate` entity.
6. Sync is idempotent: match on `area_id` / `unique_id` `area:<area_id>`; update
   entity links; **do not** wipe `rated_output_w`, `emitter_kind`, `floor_area_m2`,
   `volume_m3`, `enabled`, `price_entity` or a custom name. Missing areas are not
   deleted.

| Field | Selector | Default | Notes |
|---|---|---|---|
| `area_id` | area selector | - | Prefills `name` and suggests `demand_entity` from entities in that area |
| `name` | text | area name | Manual add does **not** yet prefill name/demand from the chosen area (auto-sync does) |
| `demand_entity` | entity | - | Filtered to sensors/attributes plausible for the chosen `demand_kind` |
| `demand_kind` | select: `percentage`, `valve_position`, `binary`, `metered_energy` | auto-detected from `demand_entity`'s unit/device_class where possible | See METHODS §12.1 |
| `temperature_entity` | entity (sensor, device_class temperature), optional | area's `climate` entity's own state, if one exists | |
| `emitter_kind` | select: `radiator`, `underfloor`, `electric`, `other` | `radiator` | |
| `rated_output_w` | number, optional | - | |
| `floor_area_m2` | number, optional | - | |
| `volume_m3` | number, optional | - | Captured; unused by any calculation (METHODS §12.4) |
| `enabled` | boolean | true | Disabling keeps history but stops daily allocation |
| `price_entity` | entity, optional | site default | Intended only for `demand_kind = metered_energy`; the add-room form currently always shows it |

Validation: `demand_entity` exists and its unit/device_class is plausible for `demand_kind`
(errors `entity_not_found`, `demand_kind_mismatch`); with `metered_energy`, the same
cumulative-sensor validation as a `generator`'s `carrier.energy_entity` applies. Removing a room
keeps its statistics (history) but stops daily updates, same convention as removing a
`generator`.

---

## Options flow

Sections (menu):

1. **Methods and season** - same fields as step 6.
2. **DHW and cooking** - defaults and summer window.
3. **History** - backfill/climatology years; button "recompute from date".
4. **Import meter readings** - paste CSV or pick a file under `/config`. Delimiter,
   decimal, date format and date/reading columns are auto-detected
   (`heatprint_core.importers.csv_readings`). A mindergas `datum;stand` export
   needs zero extra questions. A preview of the first rows is shown; only if
   headers are ambiguous does the wizard ask which column is date vs reading
   (dropdowns, never a JSON `mapping`). Choose generator and unit, confirm →
   import and recompute from the earliest imported day. The action
   `heatprint.import_readings` remains for automations.
5. **Prices and CO₂** - default factors, CO₂ sensor.
6. **Integrations** - mindergas.nl bridge: API token (password field), generator choice,
   daily push on/off. The token lives in `entry.options["integrations"]` (Home Assistant
   does not encrypt `.storage`); it is never logged and is redacted from diagnostics
   (ARCHITECTURE §9).
7. **Rooms** - auto-sync on/off (default **on**); exclude-area list; one-click
   "sync now"; default output per m² per `emitter_kind` (METHODS §12.2, shown as a clearly
   labelled placeholder/estimate); minimum days for a room fit; allocation on/off (site still
   computes `heat_space_kwh` normally when off, just skips the per-room breakdown).
   A separate menu item **Sync rooms from HA areas** previews included/skipped areas
   and refreshes the rooms dashboard (`unique_id`-based entity cards).
8. **Advanced** - override PBL parameters (TST/RER/TOP per month group) and wind
   coefficient; outlier threshold; minimum number of days for a fit.

## Reconfigure flow

Location, timezone, country, weather source/station. First-run values came from the
HA home; change them here for a second home. On a station change: fetch the weather
history again and recompute all daily records (with confirmation).

---

## Migrations and versions

- `version = 1`, `minor_version = 0`. Subentries require HA 2026.9+; on older HA
  (`entry.subentries` missing) setup raises `ConfigEntryError` with translation key
  `ha_too_old` (the HACS minimum is in `hacs.json`). This is not an issue-registry
  repair.
- Future fields get default values in `async_migrate_entry`.

## Strings and translations

All labels, descriptions and errors live in `strings.json` + `translations/en.json` and
`translations/nl.json`. Show a short "why" text (description) with every technical field, so
that the user understands the choice (for example why 18 °C is not sacred).
