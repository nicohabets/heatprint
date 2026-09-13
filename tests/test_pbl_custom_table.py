"""Custom PBL month table override (advanced options), METHODS section 4.3."""

from __future__ import annotations

import pytest

from heatprint_core.methods.degree_days import dd_pbl
from heatprint_core.methods.pbl_params import pbl_params
from heatprint_core.models import PblParams

CUSTOM = ((16.0, 1.0, 1.0), (15.0, 0.9, 1.0), (14.0, 0.8, 1.0), (13.0, 0.5, 1.0))


def test_custom_table_overrides_builtin_sets() -> None:
    assert pbl_params(1, "practical", CUSTOM).tst == 16.0
    assert pbl_params(3, "optimal", CUSTOM).rer == 0.9
    assert pbl_params(10, custom_table=CUSTOM).tst == 14.0
    assert pbl_params(7, custom_table=CUSTOM) == pbl_params(5, custom_table=CUSTOM)


def test_custom_table_used_by_dd_pbl() -> None:
    params = PblParams(custom_table=CUSTOM)
    # January: RER 1.0 * (16.0 - 5.0) = 11.0 (TOP excluded by default)
    assert dd_pbl(5.0, 1, params) == pytest.approx(11.0)
    # With TOP included the temperature-independent part is added
    assert dd_pbl(5.0, 1, PblParams(custom_table=CUSTOM, include_top=True)) == pytest.approx(12.0)


def test_custom_table_round_trips_through_json() -> None:
    params = PblParams(custom_table=CUSTOM)
    restored = PblParams.from_dict(params.to_dict())
    assert tuple(tuple(row) for row in restored.custom_table) == CUSTOM


def test_custom_table_must_have_four_groups() -> None:
    with pytest.raises(ValueError):
        pbl_params(1, custom_table=CUSTOM[:3])
