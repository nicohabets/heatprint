"""CSV importer for meter readings (DATA_MODEL section 6)."""

from __future__ import annotations

from datetime import datetime

import pytest

from heatprint_core.importers.csv_readings import (
    detect_decimal,
    detect_delimiter,
    parse_number,
    parse_readings_csv,
)

MINDERGAS = """datum;stand
01-10-2022;1234,567
02-10-2022;1236,100
03-10-2022;
04-10-2022;1240,25
"""


def test_mindergas_style_semicolon_comma() -> None:
    readings = parse_readings_csv(MINDERGAS)
    assert readings == [
        (datetime(2022, 10, 1), 1234.567),
        (datetime(2022, 10, 2), 1236.1),
        (datetime(2022, 10, 4), 1240.25),
    ]


def test_header_variants_and_auto_detection() -> None:
    text = "Datum,Meterstand\n2022-10-02,1236.10\n2022-10-01,1234.567\n"
    readings = parse_readings_csv(text, delimiter=None, decimal=None, date_format=None)
    assert readings == [(datetime(2022, 10, 1), 1234.567), (datetime(2022, 10, 2), 1236.1)]
    english = "date\treading\n01/10/2022\t1.234,5\n"
    assert parse_readings_csv(english, delimiter=None, decimal=None) == [
        (datetime(2022, 10, 1), 1234.5)
    ]


def test_headerless_and_timestamps() -> None:
    text = "01-10-2022 08:30;100,5\n02-10-2022 08:30;101,5\n"
    readings = parse_readings_csv(text)
    assert readings[0] == (datetime(2022, 10, 1, 8, 30), 100.5)
    iso = "timestamp,value\n2022-10-01T08:30:00,100.5\n"
    assert parse_readings_csv(iso, delimiter=",", decimal=".") == [
        (datetime(2022, 10, 1, 8, 30), 100.5)
    ]


def test_bom_and_unknown_header_skipped() -> None:
    text = "﻿datum;stand\n01-10-2022;1,0\n"
    assert parse_readings_csv(text) == [(datetime(2022, 10, 1), 1.0)]
    unknown = "foo;bar\n01-10-2022;1,0\nnot a date;2,0\n"
    assert parse_readings_csv(unknown) == [(datetime(2022, 10, 1), 1.0)]
    assert parse_readings_csv("") == []


def test_helpers() -> None:
    assert detect_delimiter("a;b\n1;2") == ";"
    assert detect_delimiter("a,b\n1,2") == ","
    assert detect_delimiter("a\tb") == "\t"
    assert detect_decimal(["1,5", "2,0"], ";") == ","
    assert detect_decimal(["1.5"], ",") == "."
    assert detect_decimal(["1.234,5"], ";") == ","
    assert detect_decimal(["1,234.5"], ",") == "."
    assert detect_decimal(["15"], ";") == ","
    assert parse_number("1.234,567", ",") == pytest.approx(1234.567)
    assert parse_number("1,234.5", ".") == pytest.approx(1234.5)
    assert parse_number(" 42 ", ".") == 42.0
