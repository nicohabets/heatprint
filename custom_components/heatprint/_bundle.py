"""Expose the bundled heatprint_core as a top-level package on Home Assistant OS.

HACS copies only ``custom_components/heatprint/`` into the HA config directory.
The calculation core is nested next to this file so it ships with the
integration. Home Assistant does not put that folder on ``sys.path``, and
``heatprint-core`` is not published on PyPI, so ``from heatprint_core import ...``
would fail (config flow 500) unless we add the integration directory here.

Imported first from ``__init__.py`` and ``core_api.py`` so the config flow can
load before any other integration module runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

_INTEGRATION_DIR = str(Path(__file__).resolve().parent)


def ensure_heatprint_core_on_path() -> str:
    """Put the integration directory on ``sys.path`` and return that path."""
    if _INTEGRATION_DIR not in sys.path:
        sys.path.insert(0, _INTEGRATION_DIR)
    return _INTEGRATION_DIR


ensure_heatprint_core_on_path()
