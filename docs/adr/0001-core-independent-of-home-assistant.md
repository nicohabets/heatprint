# ADR 0001 - Rekenkern los van Home Assistant

**Status:** geaccepteerd (2026-09-13)

## Context

Heatprint moet zowel als HACS-integratie werken als bruikbaar zijn in notebooks/CLI en
mogelijk andere platformen. Home Assistant-code is lastig te testen zonder de HA-testtooling
en verandert elk kwartaal.

## Besluit

Alle formules, weerproviders, conversies en analyses leven in `heatprint_core`, een pure
Python-package zonder HA-imports. De integratie in `custom_components/heatprint` doet alleen
configuratie, recorder-I/O, opslag, entiteiten en services en roept de kern aan.

## Gevolgen

- Kern is met pytest te testen (synthetische woning, referentiecase).
- Kern wordt op PyPI gepubliceerd (`heatprint-core`) en als `requirements` in de manifest gezet.
- Dubbele versiebeheer (kern + integratie); releases altijd samen.
