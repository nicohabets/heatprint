# ADR 0004 - Vier graaddagmethodes naast elkaar, huisfit als primaire

**Status:** geaccepteerd (2026-09-13)

## Context

Gebruikers komen van mindergas (klassiek 18 °C, maandfactoren). Het PBL toont dat die
methode structureel afwijkt. Een landelijk gekalibreerde methode (PBL) is beter dan klassiek
maar niet huisspecifiek. Een huisgebonden fit is het meest nauwkeurig maar vraagt ≥ 30 dagen
data en is minder herkenbaar.

## Besluit

Alle methodes (`classic`, `knmi14`, `pbl`, `house`) worden altijd berekend en opgeslagen.
De gebruiker kiest de primaire methode voor hoofdsensoren; standaard `house`, met `pbl` als
fallback zolang er geen fit is. Vergelijkingen tonen alle methodes.

## Gevolgen

- Migratie vanaf mindergas/Degree-days zonder cijferbreuk (`classic` reproduceert).
- Extra opslag (4 statistieken i.p.v. 1) - verwaarloosbaar (1 rij/dag).
- UI moet methodeverschillen uitleggen; docs bevatten een "welke methode wanneer"-pagina.
