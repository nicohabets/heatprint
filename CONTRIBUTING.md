# Contributing

Thanks for considering a contribution. Heatprint is early; the most valuable contributions
right now are **real data** (daily readings + location) that break the assumptions in
`docs/METHODS.md`, and heat-pump integrations that expose thermal energy counters.

## Ground rules

0. English only: code, comments, docstrings, documentation, commit messages and issues are
   written in English. Dutch appears only in `custom_components/heatprint/translations/nl.json`
   (the Dutch UI translation) and in quoted titles of Dutch sources.
1. Formulas live in `docs/METHODS.md` first, code second. A PR that changes a calculation
   updates METHODS.md in the same PR.
2. `heatprint_core` (at `custom_components/heatprint/heatprint_core/`) stays free of
   Home Assistant imports and heavy dependencies (ADR 0001, ADR 0002). It is nested
   only so HACS can ship it; do not import `homeassistant` from the core.
3. Every new calculation gets a unit test with a hand-checked example.
4. UI strings go in `strings.json` and both `translations/en.json` and `translations/nl.json`.

## Workflow

```bash
pip install -e ".[dev,http]"
ruff check . && ruff format --check .
pytest
```

Open an issue before large changes. Use conventional commit messages (`feat:`, `fix:`, `docs:`).
