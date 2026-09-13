"""CSV import of cumulative meter readings (DATA_MODEL section 6, mindergas export).

The generic format is ``datum;stand`` with configurable column names, date format and
decimal separator. Header variants such as ``Datum``/``Meterstand`` or
``date``/``reading`` are recognised; delimiter and decimal separator can be
auto-detected by passing None.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

#: Byte order mark that Excel puts in front of UTF-8 CSV exports.
BOM = "\ufeff"

DATE_HEADERS: tuple[str, ...] = (
    "datum",
    "date",
    "dag",
    "day",
    "timestamp",
    "tijd",
    "time",
    "datetime",
)
VALUE_HEADERS: tuple[str, ...] = (
    "stand",
    "meterstand",
    "reading",
    "value",
    "waarde",
    "meter",
    "meter_reading",
    "counter",
    "teller",
    "tellerstand",
)
DATE_FORMATS: tuple[str, ...] = (
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%d-%m-%y",
    "%d.%m.%Y",
)


def detect_delimiter(text: str) -> str:
    """Guess the delimiter from the first non-empty line (``;`` , ``,`` or tab)."""
    for line in text.splitlines():
        if line.strip():
            counts = {d: line.count(d) for d in (";", "\t", ",")}
            best = max(counts, key=lambda d: counts[d])
            return best if counts[best] > 0 else ";"
    return ";"


def detect_decimal(values: list[str], delimiter: str) -> str:
    """Guess the decimal separator from sample values (``,`` unless ``.`` is used)."""
    has_comma = any("," in v for v in values)
    has_dot = any("." in v for v in values)
    if has_comma and not has_dot:
        return ","
    if has_dot and not has_comma:
        return "."
    if has_comma and has_dot:
        # Both present: the last separator in a value is the decimal one.
        sample = next(v for v in values if "," in v and "." in v)
        return "," if sample.rfind(",") > sample.rfind(".") else "."
    return "," if delimiter == ";" else "."


def parse_number(text: str, decimal: str) -> float:
    """Parse a number with the given decimal separator (thousands separators removed)."""
    cleaned = text.strip().replace(" ", "")
    if decimal == ",":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    return float(cleaned)


def parse_date(text: str, date_format: str | None) -> datetime:
    """Parse a date/time string with ``date_format`` first, then common formats and ISO."""
    text = text.strip()
    formats = ((date_format,) if date_format else ()) + DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(text)


def _find_column(headers: list[str], wanted: str | None, candidates: tuple[str, ...]) -> int | None:
    lowered = [h.strip().lower() for h in headers]
    if wanted is not None and wanted.strip().lower() in lowered:
        return lowered.index(wanted.strip().lower())
    for candidate in candidates:
        if candidate in lowered:
            return lowered.index(candidate)
    for index, header in enumerate(lowered):
        if any(header.startswith(candidate) for candidate in candidates):
            return index
    return None


def parse_readings_csv(
    text: str,
    date_col: str | None = "datum",
    value_col: str | None = "stand",
    date_format: str | None = "%d-%m-%Y",
    delimiter: str | None = ";",
    decimal: str | None = ",",
) -> list[tuple[datetime, float]]:
    """Parse CSV text into sorted ``(datetime, reading)`` pairs.

    Pass None for ``delimiter`` / ``decimal`` to auto-detect them. When the configured
    columns are not found, common header names are tried; a header-less two-column file
    is read as ``date, value``. Rows with an empty or unparsable value are skipped.
    Dates without a time are interpreted as local midnight (naive datetimes).
    """
    text = text.lstrip(BOM)
    if delimiter is None:
        delimiter = detect_delimiter(text)
    rows = [
        row
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        if any(c.strip() for c in row)
    ]
    if not rows:
        return []

    header = rows[0]
    date_index = _find_column(header, date_col, DATE_HEADERS)
    value_index = _find_column(header, value_col, VALUE_HEADERS)
    if date_index is None or value_index is None:
        # No usable header: assume date, value in the first two columns of every row.
        date_index, value_index = 0, 1
        data_rows = rows
        try:
            parse_date(rows[0][0], date_format)
        except (ValueError, IndexError):
            data_rows = rows[1:]  # first row was a header we did not recognise
    else:
        data_rows = rows[1:]

    if decimal is None:
        samples = [
            row[value_index]
            for row in data_rows
            if len(row) > value_index and row[value_index].strip()
        ]
        decimal = detect_decimal(samples, delimiter)

    result: list[tuple[datetime, float]] = []
    skipped = 0
    for row in data_rows:
        if len(row) <= max(date_index, value_index):
            skipped += 1
            continue
        date_text, value_text = row[date_index], row[value_index]
        if not date_text.strip() or not value_text.strip():
            skipped += 1
            continue
        try:
            stamp = parse_date(date_text, date_format)
            value = parse_number(value_text, decimal)
        except ValueError:
            skipped += 1
            continue
        result.append((stamp, value))
    if skipped:
        _LOGGER.debug("CSV import: %d row(s) skipped", skipped)
    result.sort(key=lambda item: item[0])
    return result
