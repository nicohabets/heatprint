"""Monthly parameters of the PBL 2022 / KEV-SJV method (METHODS section 4.3).

Two parameter sets:

- ``practical`` (PBL Table 3.4: practical model, De Bilt, temperature + wind, 1 day of
  history) - the default.
- ``optimal`` (PBL Table 3.3: 6 stations + sun).

Each month belongs to one of four groups: Dec/Jan/Feb, Mar/Nov, Apr/Oct and May-Sep.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PblMonthParams:
    """Month parameters: ``TST`` (threshold temperature, degrees C), ``RER`` and ``TOP``."""

    tst: float
    rer: float
    top: float


#: Month group per month number: 0 = Dec/Jan/Feb, 1 = Mar/Nov, 2 = Apr/Oct, 3 = May-Sep.
MONTH_GROUP: dict[int, int] = {
    12: 0,
    1: 0,
    2: 0,
    3: 1,
    11: 1,
    4: 2,
    10: 2,
    5: 3,
    6: 3,
    7: 3,
    8: 3,
    9: 3,
}

#: PBL Table 3.4 - practical model (temperature + wind, 1 day history, De Bilt).
PBL_PRACTICAL: tuple[PblMonthParams, ...] = (
    PblMonthParams(tst=17.01, rer=1.00, top=1.30),
    PblMonthParams(tst=15.26, rer=1.02, top=1.30),
    PblMonthParams(tst=15.10, rer=0.79, top=1.30),
    PblMonthParams(tst=13.92, rer=0.61, top=1.30),
)

#: PBL Table 3.3 - optimal model (6 stations + sun).
PBL_OPTIMAL: tuple[PblMonthParams, ...] = (
    PblMonthParams(tst=14.91, rer=1.00, top=1.32),
    PblMonthParams(tst=15.09, rer=0.96, top=1.32),
    PblMonthParams(tst=15.52, rer=0.82, top=1.32),
    PblMonthParams(tst=15.15, rer=0.73, top=1.32),
)

PARAMETER_SETS: dict[str, tuple[PblMonthParams, ...]] = {
    "practical": PBL_PRACTICAL,
    "optimal": PBL_OPTIMAL,
}


def pbl_params(month: int, parameter_set: str = "practical") -> PblMonthParams:
    """Return ``(TST, RER, TOP)`` for a month (1-12) and parameter set."""
    if month not in MONTH_GROUP:
        raise ValueError(f"invalid month: {month}")
    try:
        table = PARAMETER_SETS[parameter_set]
    except KeyError as exc:
        raise ValueError(f"unknown PBL parameter set: {parameter_set!r}") from exc
    return table[MONTH_GROUP[month]]
