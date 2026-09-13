# ADR 0005 - Allocate site heat to rooms by demand signal, not a design heat-loss calculation

**Status:** accepted (2026-09-13)

## Context

Nico wants per-room heat loss and per-room/total heating cost. Home Assistant users rarely have
a per-room heat meter; what they do have is a thermostat integration (Tado/`tado_ce`, Zigbee
TRVs, others) exposing a room-level heating-demand percentage, valve position, or on/off state.
A physically rigorous per-room heat-loss figure (EN 12831-style) needs envelope areas, U-values
and design conditions Heatprint does not have and is not positioned to collect.

## Decision

Allocate the site's already-computed `heat_space_kwh` (METHODS §5-6) across configured rooms in
proportion to each room's weighted daily heating-demand integral (METHODS §12), with an
"unallocated" bucket for whatever is not covered. Fit an apparent per-room heat loss (UA) and
balance temperature with the same energy-signature method already used at site level (§7),
reusing the site's TAC rather than inventing a per-room outdoor climate. Cost is allocated the
same way, from the generator prices already in the data model. Every room-level figure is
presented as an estimate for relative, within-house comparison - not a certified design
heat-loss calculation - and rooms without a rated output default to an explicitly flagged
weight of 1.

## Consequences

- No new physical measurement is required from the user beyond what their existing thermostat
  integration already exposes; the feature is usable the day a `room` subentry is added, though
  the fit itself needs a season of data (§12.4).
- The apparent per-room UA includes interzonal heat exchange and depends on how faithfully the
  demand signal tracks delivered heat - a real limitation that must stay visible in the UI
  (§12.9), not a temporary caveat to remove later.
- A room's history cannot be backfilled beyond wherever its demand entity's statistics begin,
  unlike KNMI-based site weather; this is the same limitation already accepted for `ha_sensors`
  weather sources.
- The feature is deliberately integration-agnostic (§12.6): Tado is the first verified adapter
  on Nico's own instance, not a hard dependency; other thermostat/TRV integrations map onto the
  same `demand_kind` abstraction.
- Default emitter-output figures (§12.2) are unverified placeholders until checked against a
  published source (ROADMAP research item) - the same honesty standard already applied to the
  PBL wind coefficient (§3).
