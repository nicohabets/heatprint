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
from dataclasses import dataclass, field
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


@dataclass
class CsvInspection:
    """Result of auto-detecting a meter-reading CSV (wizard + tests)."""

    delimiter: str
    decimal: str
    date_format: str | None
    date_column: str | None
    reading_column: str | None
    headers: list[str] = field(default_factory=list)
    headerless: bool = False
    ambiguous: bool = False
    readings: list[tuple[datetime, float]] = field(default_factory=list)
    skipped: int = 0
    error: str | None = None

    @property
    def preview(self) -> list[tuple[str, str]]:
        """First five readings as ``(ISO date, reading)`` display pairs."""
        rows: list[tuple[str, str]] = []
        for stamp, value in self.readings[:5]:
            rows.append((stamp.isoformat(sep=" "), f"{value:.6f}".rstrip("0").rstrip(".")))
        return rows


def detect_date_format(samples: list[str]) -> str | None:
    """Return the first DATE_FORMATS entry that parses every sample, if any."""
    cleaned = [sample.strip() for sample in samples if sample.strip()]
    if not cleaned:
        return None
    for fmt in DATE_FORMATS:
        try:
            for sample in cleaned:
                datetime.strptime(sample, fmt)
        except ValueError:
            continue
        else:
            return fmt
    return None


def inspect_readings_csv(
    text: str,
    *,
    date_col: str | None = None,
    value_col: str | None = None,
    date_format: str | None = None,
    delimiter: str | None = None,
    decimal: str | None = None,
) -> CsvInspection:
    """Auto-detect delimiter, decimal, date format and columns; parse readings.

    ``ambiguous`` is True when headers exist but date/reading columns are not
    uniquely recognised (more than two columns and no known header names).
    mindergas ``datum;stand`` is never ambiguous.
    """
    text = text.lstrip(BOM)
    if not text.strip():
        return CsvInspection(
            delimiter=";",
            decimal=",",
            date_format=None,
            date_column=None,
            reading_column=None,
            error="empty",
        )
    if delimiter is None:
        delimiter = detect_delimiter(text)
    rows = [
        row
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        return CsvInspection(
            delimiter=delimiter,
            decimal=decimal or ",",
            date_format=date_format,
            date_column=date_col,
            reading_column=value_col,
            error="empty",
        )

    header = [cell.strip() for cell in rows[0]]
    date_index = _find_column(header, date_col, DATE_HEADERS)
    value_index = _find_column(header, value_col, VALUE_HEADERS)
    matched_date = date_index is not None
    matched_value = value_index is not None
    headerless = False
    ambiguous = False
    data_rows: list[list[str]]
    headers = header

    if matched_date and matched_value:
        data_rows = rows[1:]
    elif not matched_date and not matched_value and date_col is None and value_col is None:
        try:
            parse_date(rows[0][0], date_format)
            headerless = True
            data_rows = rows
            headers = [f"column_{index + 1}" for index in range(len(rows[0]))]
        except (ValueError, IndexError):
            data_rows = rows[1:]
        date_index, value_index = 0, 1
        ambiguous = len(rows[0]) > 2
    else:
        data_rows = rows[1:]
        if date_index is None:
            date_index = 0 if value_index != 0 else 1
        if value_index is None:
            value_index = 1 if date_index != 1 else 0
        ambiguous = True

    if decimal is None:
        samples = [
            row[value_index]
            for row in data_rows
            if len(row) > value_index and row[value_index].strip()
        ]
        decimal = detect_decimal(samples, delimiter)

    date_samples = [
        row[date_index] for row in data_rows if len(row) > date_index and row[date_index].strip()
    ][:8]
    if date_format is None:
        date_format = detect_date_format(date_samples)

    readings: list[tuple[datetime, float]] = []
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
        readings.append((stamp, value))
    readings.sort(key=lambda item: item[0])

    date_column = headers[date_index] if date_index < len(headers) else None
    reading_column = headers[value_index] if value_index < len(headers) else None
    error = "no_rows" if not readings else None
    return CsvInspection(
        delimiter=delimiter,
        decimal=decimal,
        date_format=date_format,
        date_column=date_column,
        reading_column=reading_column,
        headers=headers,
        headerless=headerless,
        ambiguous=ambiguous and error is None,
        readings=readings,
        skipped=skipped,
        error=error,
    )
