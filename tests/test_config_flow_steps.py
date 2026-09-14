"""Config flow only exposes live first-run / reconfigure / options / subentry steps."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FLOW = REPO / "custom_components" / "heatprint" / "config_flow.py"

# Dead first-run wizard (situation → summary) must stay deleted.
DEAD_CONFIG_STEPS = {
    "situation",
    "generator",
    "generator_details",
    "generator_more",
    "dhw",
    "methods",
    "history",
    "summary",
}

# Reached from async_step_user or Reconfigure (weather is Reconfigure-only).
LIVE_CONFIG_STEPS = {
    "user",
    "weather_nl",
    "weather_intl",
    "weather_sensors",
    "reconfigure",
    "reconfigure_confirm",
}


def _class_step_ids(tree: ast.Module, class_name: str) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name[len("async_step_") :]
                for item in node.body
                if isinstance(item, ast.AsyncFunctionDef) and item.name.startswith("async_step_")
            }
    raise AssertionError(f"class {class_name} not found")


def _function_names(tree: ast.Module) -> set[str]:
    return {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_config_flow_only_exposes_live_steps() -> None:
    tree = ast.parse(FLOW.read_text(encoding="utf-8"))
    steps = _class_step_ids(tree, "HeatprintConfigFlow")
    assert steps == LIVE_CONFIG_STEPS
    assert DEAD_CONFIG_STEPS.isdisjoint(steps)


def test_dead_wizard_helpers_are_gone() -> None:
    source = FLOW.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = _function_names(tree)
    for dead in ("SITUATION_DRAFTS",):
        assert dead not in source
    assert "_dhw_summary" not in names
    config_steps = _class_step_ids(tree, "HeatprintConfigFlow")
    for step in DEAD_CONFIG_STEPS:
        assert step not in config_steps


def test_options_and_subentries_keep_their_live_steps() -> None:
    tree = ast.parse(FLOW.read_text(encoding="utf-8"))
    options = _class_step_ids(tree, "HeatprintOptionsFlow")
    assert {
        "init",
        "methods",
        "dhw",
        "history",
        "import_readings",
        "pricing",
        "integrations",
        "rooms",
        "sync_rooms",
        "advanced",
    }.issubset(options)
    generator = _class_step_ids(tree, "GeneratorSubentryFlowHandler")
    assert {"user", "details", "reconfigure", "reconfigure_details"}.issubset(generator)
    assert _class_step_ids(tree, "MeasureSubentryFlowHandler") >= {"user", "reconfigure"}
    assert _class_step_ids(tree, "RoomSubentryFlowHandler") >= {"user", "reconfigure"}


def test_room_add_does_not_force_price_entity() -> None:
    """Manual room add used to pass show_price or True; cost is deferred."""
    source = FLOW.read_text(encoding="utf-8")
    assert "show_price or True" not in source
    assert "show_price=False" in source


def test_name_exists_string_removed() -> None:
    strings = (REPO / "custom_components" / "heatprint" / "strings.json").read_text(
        encoding="utf-8"
    )
    assert '"name_exists"' not in strings
