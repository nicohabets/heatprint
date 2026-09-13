# ADR 0002 - Geen zware dependencies in de kern

**Status:** geaccepteerd (2026-09-13)

## Context

Home Assistant draait ook op kleine hardware (HA Green/Yellow, Raspberry Pi). numpy/scipy/pandas
zijn groot, vertragen installatie en geven wheel-problemen op sommige platformen. De
berekeningen (OLS met één of twee regressoren, rasterzoek, bootstrap over ~200 dagen) zijn
klein.

## Besluit

`heatprint_core` heeft geen verplichte runtime-dependencies. OLS, rasterzoek en bootstrap zijn in
pure Python geïmplementeerd. HTTP-clients zijn optioneel (`aiohttp` via extra `http`); in HA
wordt de aiohttp-sessie van HA doorgegeven.

## Gevolgen

- Iets meer eigen code (kleinste-kwadraten, t-kwantielen als tabel/benadering).
- Snelle installatie via HACS, geen compilatie.
- Voor zware analyses buiten HA kan een gebruiker de dagrecords exporteren naar pandas.
