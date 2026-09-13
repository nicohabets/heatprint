"""HACS packaging: the core ships inside the integration (no unpublished PyPI pin)."""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTEGRATION = REPO / "custom_components" / "heatprint"
CORE = INTEGRATION / "heatprint_core"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_has_no_unpublished_pypi_requirement() -> None:
    manifest = _load_json(INTEGRATION / "manifest.json")
    assert manifest["domain"] == "heatprint"
    assert manifest["config_flow"] is True
    requirements = manifest.get("requirements", [])
    assert requirements == []
    assert not any("heatprint-core" in item for item in requirements)


def test_integration_and_core_versions_match() -> None:
    manifest = _load_json(INTEGRATION / "manifest.json")
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    core_init = (CORE / "__init__.py").read_text(encoding="utf-8")
    project_version = re.search(r'(?m)^version = "([^"]+)"', pyproject)
    core_version = re.search(r'(?m)^__version__ = "([^"]+)"', core_init)
    assert project_version and core_version
    assert manifest["version"] == project_version.group(1) == core_version.group(1)


def test_hacs_json_matches_ha_minimum_and_domain_folder() -> None:
    hacs = _load_json(REPO / "hacs.json")
    assert hacs["name"] == "Heatprint"
    assert hacs["homeassistant"] == "2026.9.0"
    assert hacs.get("hide_default_branch") is False
    assert INTEGRATION.is_dir()
    assert (INTEGRATION / "manifest.json").is_file()
    assert (INTEGRATION / "config_flow.py").is_file()
    assert (INTEGRATION / "brand" / "icon.png").is_file()


def test_heatprint_core_is_nested_in_the_integration() -> None:
    assert (CORE / "__init__.py").is_file()
    assert (CORE / "pipeline.py").is_file()
    assert not (REPO / "heatprint_core").exists()


def test_bundle_bootstrap_imports_heatprint_core_from_integration_dir() -> None:
    """Simulate HA OS: only the integration folder is on sys.path (no PyPI wheel)."""
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "heatprint_core" or name.startswith("heatprint_core.")
    }
    saved_path = list(sys.path)
    try:
        for name in list(saved_modules):
            del sys.modules[name]
        sys.path = [str(INTEGRATION), *saved_path]
        import heatprint_core

        assert Path(heatprint_core.__file__).resolve() == (CORE / "__init__.py").resolve()
        from heatprint_core import Site, build_daily_records

        assert callable(build_daily_records)
        assert Site.__name__ == "Site"
    finally:
        sys.path[:] = saved_path
        for name in list(sys.modules):
            if name == "heatprint_core" or name.startswith("heatprint_core."):
                del sys.modules[name]
        sys.modules.update(saved_modules)
        importlib.invalidate_caches()


def test_config_flow_imports_core_api_which_imports_heatprint_core() -> None:
    """The 500 path: HA loads config_flow, which pulls in core_api → heatprint_core."""
    flow_source = (INTEGRATION / "config_flow.py").read_text(encoding="utf-8")
    flow_tree = ast.parse(flow_source)
    core_api_imports = [
        node
        for node in ast.walk(flow_tree)
        if isinstance(node, ast.ImportFrom) and node.module == "core_api"
    ]
    assert core_api_imports, "config_flow.py must import .core_api"

    api_tree = ast.parse((INTEGRATION / "core_api.py").read_text(encoding="utf-8"))
    core_imports = [
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("heatprint_core")
    ]
    assert core_imports, "core_api.py must import heatprint_core"


def test_bundled_core_has_no_homeassistant_imports() -> None:
    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("homeassistant")
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("homeassistant")
