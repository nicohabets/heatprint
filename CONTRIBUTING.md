# Contributing

Thanks for considering a contribution. Heatprint is early; the most valuable contributions
right now are **real data** (daily readings + location) that break the assumptions in
`docs/METHODS.md`, and heat-pump integrations that expose thermal energy counters.

## Ground rules

1. Formulas live in `docs/METHODS.md` first, code second. A PR that changes a calculation
   updates METHODS.md in the same PR.
2. `heatprint_core` stays free of Home Assistant imports and heavy dependencies (ADR 0002).
3. Every new calculation gets a unit test with a hand-checked example.
4. UI strings go in `strings.json` and both `translations/en.json` and `translations/nl.json`.

## Workflow

```bash
pip install -e ".[dev,http]"
ruff check . && ruff format --check .
pytest
```

Open an issue before large changes. Use conventional commit messages (`feat:`, `fix:`, `docs:`).
