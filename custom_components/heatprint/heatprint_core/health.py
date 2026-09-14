"""Data-source health checks (METHODS section 14).

Threshold rules, not a statistical model: no numpy (ADR 0002). Each rule is one
sentence. The Home Assistant layer turns each finding into a repair and lists
open checks on ``sensor.<site>_data_quality``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from .constants import (
    HEALTH_IMPLAUSIBLE_LOOKBACK_DAYS,
    HEALTH_IMPLAUSIBLE_MIN_SAMPLES,
    HEALTH_IMPLAUSIBLE_MULTIPLE,
    HEALTH_PROVISIONAL_WINDOW_DAYS,
    HEALTH_SCALE_DD_COMPARABLE_RATIO,
    HEALTH_SCALE_MIN_SAMPLES,
    HEALTH_SCALE_RATIO,
    HEALTH_SCALE_WINDOW_DAYS,
    HEALTH_STUCK_DAYS,
    KNMI_STATIONS,
)
from .flags import Flag
from .models import DailyRecord, DailyRoomRecord, DemandKind, Provider, Site


class HealthCheckName(StrEnum):
    """Named checks from METHODS section 14."""

    STUCK_VALUE = "stuck_value"
    IMPLAUSIBLE_VALUE = "implausible_value"
    SCALE_DRIFT = "scale_drift"
    WEATHER_STALLED = "weather_stalled"


class HealthSourceKind(StrEnum):
    """What the finding names (generator, room demand entity, or weather source)."""

    GENERATOR = "generator"
    ROOM = "room"
    WEATHER = "weather"


HINTS: dict[HealthCheckName, str] = {
    HealthCheckName.STUCK_VALUE: "confirm the meter integration is still polling",
    HealthCheckName.IMPLAUSIBLE_VALUE: (
        "check yesterday's reading and whether the sensor unit is still correct"
    ),
    HealthCheckName.SCALE_DRIFT: (
        "check whether an integration update changed the sensor unit or precision"
    ),
    HealthCheckName.WEATHER_STALLED: (
        "the weather provider is still returning provisional data; check the station"
    ),
}


@dataclass(frozen=True)
class HealthCheckConfig:
    """Tunable thresholds (METHODS §14 defaults)."""

    stuck_days: int = HEALTH_STUCK_DAYS
    implausible_multiple: float = HEALTH_IMPLAUSIBLE_MULTIPLE
    implausible_lookback_days: int = HEALTH_IMPLAUSIBLE_LOOKBACK_DAYS
    implausible_min_samples: int = HEALTH_IMPLAUSIBLE_MIN_SAMPLES
    scale_window_days: int = HEALTH_SCALE_WINDOW_DAYS
    scale_ratio: float = HEALTH_SCALE_RATIO
    scale_min_samples: int = HEALTH_SCALE_MIN_SAMPLES
    scale_dd_comparable_ratio: float = HEALTH_SCALE_DD_COMPARABLE_RATIO
    provisional_window_days: Mapping[str, int] | None = None

    def window_for(self, provider: str) -> int:
        """Return the normal provisional-data window for ``provider``."""
        table = self.provisional_window_days or HEALTH_PROVISIONAL_WINDOW_DAYS
        return int(table.get(provider, HEALTH_PROVISIONAL_WINDOW_DAYS.get("knmi", 2)))


@dataclass(frozen=True)
class WeatherSourceRef:
    """Weather source named in ``WEATHER_STALLED`` / degree-day findings."""

    provider: str
    source_id: str
    name: str

    @classmethod
    def from_site(cls, site: Site) -> WeatherSourceRef:
        """Build a ref from the site's weather config."""
        provider = (
            site.weather.provider.value
            if isinstance(site.weather.provider, Provider)
            else str(site.weather.provider)
        )
        if provider == Provider.KNMI.value:
            station = site.weather.station_id or "unknown"
            station_name = _knmi_station_name(station)
            return cls(
                provider=provider,
                source_id=f"knmi_{station}",
                name=f"KNMI {station_name} ({station})",
            )
        if provider == Provider.OPEN_METEO.value:
            return cls(provider=provider, source_id="open_meteo", name="Open-Meteo")
        if provider == Provider.HA_SENSORS.value:
            return cls(
                provider=provider,
                source_id="ha_sensors",
                name="Home Assistant weather sensors",
            )
        return cls(provider=provider, source_id=provider or "weather", name=provider or "weather")


@dataclass(frozen=True)
class HealthFinding:
    """One open health check (one repair, one ``open_health_checks`` row)."""

    check: HealthCheckName
    source_kind: HealthSourceKind
    source_id: str
    source_name: str
    hint: str
    series: str | None = None
    value: float | None = None
    typical: float | None = None

    def issue_id(self, site_id: str) -> str:
        """Stable HA issue id: ``health_{site}_{check}_{kind}_{source}``."""
        return f"health_{site_id}_{self.check}_{self.source_kind}_{self.source_id}"

    def to_attribute(self) -> dict[str, str]:
        """JSON-able row for ``sensor.<site>_data_quality`` attributes."""
        row = {
            "check": self.check.value,
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "hint": self.hint,
        }
        if self.series:
            row["series"] = self.series
        return row


def findings_as_attributes(findings: Sequence[HealthFinding]) -> list[dict[str, str]]:
    """Sort and serialise findings for the data-quality sensor."""
    ordered = sorted(
        findings, key=lambda item: (item.check.value, item.source_kind.value, item.source_id)
    )
    return [item.to_attribute() for item in ordered]


def health_issue_prefix(site_id: str) -> str:
    """Prefix of every METHODS §14 repair id for ``site_id``."""
    return f"health_{site_id}_"


def stale_health_issue_ids(
    existing_ids: Sequence[str], wanted_ids: set[str], site_id: str
) -> set[str]:
    """Issue ids that belong to this site's health checks but are no longer open."""
    prefix = health_issue_prefix(site_id)
    return {
        issue_id
        for issue_id in existing_ids
        if issue_id.startswith(prefix) and issue_id not in wanted_ids
    }


def run_health_checks(
    records: Sequence[DailyRecord],
    *,
    site: Site | None = None,
    room_records: Sequence[DailyRoomRecord] | None = None,
    weather_source: WeatherSourceRef | None = None,
    config: HealthCheckConfig | None = None,
    as_of: date | None = None,
    primary_method: str | None = None,
) -> list[HealthFinding]:
    """Run METHODS §14 checks for ``as_of`` (default: last record date).

    Daily, over every configured generator, room demand entity and weather source.
    """
    cfg = config or HealthCheckConfig()
    if not records:
        return []
    by_date = {record.date: record for record in records}
    checked = as_of or max(by_date)
    method = primary_method or (site.methods.primary if site is not None else "pbl")
    weather = weather_source or (WeatherSourceRef.from_site(site) if site is not None else None)
    findings: list[HealthFinding] = []

    generator_names = (
        {generator.id: generator.name for generator in site.generators} if site is not None else {}
    )
    room_by_id = {room.id: room for room in site.rooms} if site is not None else {}

    findings.extend(_stuck_generators(by_date, checked, cfg, generator_names, site))
    findings.extend(_stuck_rooms(room_records or [], checked, by_date, cfg, room_by_id))
    findings.extend(_implausible_generators(by_date, checked, cfg, generator_names, site))
    findings.extend(_implausible_degree_days(by_date, checked, cfg, method, weather))
    findings.extend(_implausible_rooms(room_records or [], checked, cfg, room_by_id))
    findings.extend(_scale_generators(by_date, checked, cfg, method, generator_names, site))
    findings.extend(_scale_rooms(room_records or [], checked, by_date, cfg, method, room_by_id))
    if weather is not None:
        findings.extend(_weather_stalled(by_date, checked, cfg, weather))

    return _unique(findings)


def _unique(findings: Sequence[HealthFinding]) -> list[HealthFinding]:
    seen: set[tuple[str, str, str]] = set()
    result: list[HealthFinding] = []
    for finding in findings:
        key = (finding.check.value, finding.source_kind.value, finding.source_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _knmi_station_name(station_id: str) -> str:
    try:
        key = int(station_id)
    except (TypeError, ValueError):
        return str(station_id)
    row = KNMI_STATIONS.get(key)
    return row[0] if row else str(station_id)


def _median(values: Sequence[float]) -> float:
    """Odd/even median without numpy."""
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _dates_back(end: date, days: int) -> list[date]:
    return [end - timedelta(days=offset) for offset in range(days)]


def _series_on(
    by_date: Mapping[date, DailyRecord],
    days: Sequence[date],
    getter,
) -> list[float]:
    values: list[float] = []
    for day in days:
        record = by_date.get(day)
        if record is None:
            continue
        value = getter(record)
        if value is not None:
            values.append(float(value))
    return values


def _site_heating(by_date: Mapping[date, DailyRecord], days: Sequence[date]) -> bool:
    """True when any generator produced space heat on any of ``days``."""
    for day in days:
        record = by_date.get(day)
        if record is None:
            continue
        if record.heat_space_kwh > 0:
            return True
        if any(energy.heat_space_kwh > 0 for energy in record.heat_by_generator.values()):
            return True
    return False


def _generator_meter(record: DailyRecord, generator_id: str) -> float | None:
    energy = record.heat_by_generator.get(generator_id)
    if energy is None:
        return None
    if energy.carrier_amount is not None:
        return float(energy.carrier_amount)
    if energy.electric_kwh is not None:
        return float(energy.electric_kwh)
    return float(energy.heat_total_kwh)


def _generator_heat(record: DailyRecord, generator_id: str) -> float | None:
    energy = record.heat_by_generator.get(generator_id)
    if energy is None:
        return None
    return float(energy.heat_space_kwh)


def _degree_days(record: DailyRecord, method: str) -> float | None:
    if method in record.dd:
        return float(record.dd[method])
    if record.dd:
        return float(next(iter(record.dd.values())))
    return None


def _generator_ids(by_date: Mapping[date, DailyRecord], site: Site | None) -> list[str]:
    if site is not None:
        return [generator.id for generator in site.generators]
    found: set[str] = set()
    for record in by_date.values():
        found.update(record.heat_by_generator)
    return sorted(found)


def _generator_name(generator_id: str, names: Mapping[str, str], site: Site | None) -> str:
    if generator_id in names:
        return names[generator_id]
    if site is not None:
        try:
            return site.generator(generator_id).name
        except KeyError:
            pass
    return generator_id


def _room_name(room_id: str, rooms: Mapping[str, object]) -> str:
    room = rooms.get(room_id)
    name = getattr(room, "name", None) if room is not None else None
    return str(name) if name else room_id


def _room_series(
    room_records: Sequence[DailyRoomRecord], room_id: str
) -> dict[date, DailyRoomRecord]:
    return {record.date: record for record in room_records if record.room_id == room_id}


def _room_value(record: DailyRoomRecord) -> float | None:
    if record.demand_integral is not None:
        return float(record.demand_integral)
    if record.heat_room_kwh is not None:
        return float(record.heat_room_kwh)
    return None


def _finding(
    check: HealthCheckName,
    kind: HealthSourceKind,
    source_id: str,
    source_name: str,
    *,
    series: str | None = None,
    value: float | None = None,
    typical: float | None = None,
) -> HealthFinding:
    return HealthFinding(
        check=check,
        source_kind=kind,
        source_id=source_id,
        source_name=source_name,
        hint=HINTS[check],
        series=series,
        value=value,
        typical=typical,
    )


def _stuck_generators(
    by_date: Mapping[date, DailyRecord],
    as_of: date,
    cfg: HealthCheckConfig,
    names: Mapping[str, str],
    site: Site | None,
) -> list[HealthFinding]:
    days = _dates_back(as_of, cfg.stuck_days)
    if not _site_heating(by_date, days):
        return []
    findings: list[HealthFinding] = []
    for generator_id in _generator_ids(by_date, site):
        values = [_generator_meter(by_date[day], generator_id) for day in days if day in by_date]
        if len(values) < cfg.stuck_days:
            continue
        if any(value is None for value in values):
            continue
        if any(float(value) != 0.0 for value in values if value is not None):
            continue
        findings.append(
            _finding(
                HealthCheckName.STUCK_VALUE,
                HealthSourceKind.GENERATOR,
                generator_id,
                _generator_name(generator_id, names, site),
                series="carrier",
                value=0.0,
            )
        )
    return findings


def _stuck_rooms(
    room_records: Sequence[DailyRoomRecord],
    as_of: date,
    by_date: Mapping[date, DailyRecord],
    cfg: HealthCheckConfig,
    rooms: Mapping[str, object],
) -> list[HealthFinding]:
    """``STUCK_VALUE`` on metered-energy rooms only (cumulative meters)."""
    days = _dates_back(as_of, cfg.stuck_days)
    if not _site_heating(by_date, days):
        return []
    findings: list[HealthFinding] = []
    room_ids = {record.room_id for record in room_records}
    for room_id in sorted(room_ids):
        room = rooms.get(room_id)
        if room is not None and getattr(room, "demand_kind", None) is not DemandKind.METERED_ENERGY:
            continue
        if room is None:
            # Without config, only treat a room as metered when heat_room_kwh is the series.
            sample = next((item for item in room_records if item.room_id == room_id), None)
            if sample is None or sample.heat_room_kwh is None:
                continue
        series = _room_series(room_records, room_id)
        values = [_room_value(series[day]) for day in days if day in series]
        if len(values) < cfg.stuck_days or any(value is None for value in values):
            continue
        if any(float(value) != 0.0 for value in values if value is not None):
            continue
        findings.append(
            _finding(
                HealthCheckName.STUCK_VALUE,
                HealthSourceKind.ROOM,
                room_id,
                _room_name(room_id, rooms),
                series="demand",
                value=0.0,
            )
        )
    return findings


def _implausible(
    today: float | None,
    history: Sequence[float],
    cfg: HealthCheckConfig,
) -> tuple[bool, float | None]:
    if today is None or today <= 0:
        return False, None
    if len(history) < cfg.implausible_min_samples:
        return False, None
    typical = _median(history)
    if typical <= 0:
        return False, typical
    return today > cfg.implausible_multiple * typical, typical


def _lookback_days(as_of: date, cfg: HealthCheckConfig) -> list[date]:
    return [
        as_of - timedelta(days=offset) for offset in range(1, cfg.implausible_lookback_days + 1)
    ]


def _implausible_generators(
    by_date: Mapping[date, DailyRecord],
    as_of: date,
    cfg: HealthCheckConfig,
    names: Mapping[str, str],
    site: Site | None,
) -> list[HealthFinding]:
    today = by_date.get(as_of)
    if today is None:
        return []
    history_days = _lookback_days(as_of, cfg)
    findings: list[HealthFinding] = []
    for generator_id in _generator_ids(by_date, site):
        current = _generator_heat(today, generator_id)
        history = _series_on(
            by_date, history_days, lambda rec, gid=generator_id: _generator_heat(rec, gid)
        )
        fired, typical = _implausible(current, history, cfg)
        if fired:
            findings.append(
                _finding(
                    HealthCheckName.IMPLAUSIBLE_VALUE,
                    HealthSourceKind.GENERATOR,
                    generator_id,
                    _generator_name(generator_id, names, site),
                    series="heat_space_kwh",
                    value=current,
                    typical=typical,
                )
            )
    return findings


def _implausible_degree_days(
    by_date: Mapping[date, DailyRecord],
    as_of: date,
    cfg: HealthCheckConfig,
    method: str,
    weather: WeatherSourceRef | None,
) -> list[HealthFinding]:
    today = by_date.get(as_of)
    if today is None or weather is None:
        return []
    current = _degree_days(today, method)
    history = _series_on(by_date, _lookback_days(as_of, cfg), lambda rec: _degree_days(rec, method))
    fired, typical = _implausible(current, history, cfg)
    if not fired:
        return []
    return [
        _finding(
            HealthCheckName.IMPLAUSIBLE_VALUE,
            HealthSourceKind.WEATHER,
            weather.source_id,
            weather.name,
            series=f"dd_{method}",
            value=current,
            typical=typical,
        )
    ]


def _implausible_rooms(
    room_records: Sequence[DailyRoomRecord],
    as_of: date,
    cfg: HealthCheckConfig,
    rooms: Mapping[str, object],
) -> list[HealthFinding]:
    findings: list[HealthFinding] = []
    history_days = set(_lookback_days(as_of, cfg))
    for room_id in sorted({record.room_id for record in room_records}):
        series = _room_series(room_records, room_id)
        today = series.get(as_of)
        current = _room_value(today) if today is not None else None
        history = [
            value
            for day, record in series.items()
            if day in history_days and (value := _room_value(record)) is not None
        ]
        fired, typical = _implausible(current, history, cfg)
        if fired:
            findings.append(
                _finding(
                    HealthCheckName.IMPLAUSIBLE_VALUE,
                    HealthSourceKind.ROOM,
                    room_id,
                    _room_name(room_id, rooms),
                    series="demand",
                    value=current,
                    typical=typical,
                )
            )
    return findings


def _scale_ratio(
    recent: Sequence[float], older: Sequence[float], cfg: HealthCheckConfig
) -> float | None:
    if len(recent) < cfg.scale_min_samples or len(older) < cfg.scale_min_samples:
        return None
    recent_med = _median(recent)
    older_med = _median(older)
    if recent_med <= 0 or older_med <= 0:
        return None
    return recent_med / older_med


def _dd_comparable(
    by_date: Mapping[date, DailyRecord],
    recent_days: Sequence[date],
    older_days: Sequence[date],
    method: str,
    cfg: HealthCheckConfig,
) -> bool:
    """True when both windows look like the same weather regime (not a season flip)."""
    recent = _series_on(by_date, recent_days, lambda rec: _degree_days(rec, method))
    older = _series_on(by_date, older_days, lambda rec: _degree_days(rec, method))
    if len(recent) < cfg.scale_min_samples or len(older) < cfg.scale_min_samples:
        return False
    recent_med = _median(recent)
    older_med = _median(older)
    if recent_med <= 0 or older_med <= 0:
        return False
    ratio = max(recent_med, older_med) / min(recent_med, older_med)
    return ratio <= cfg.scale_dd_comparable_ratio


def _scale_windows(as_of: date, cfg: HealthCheckConfig) -> tuple[list[date], list[date]]:
    recent = [as_of - timedelta(days=offset) for offset in range(cfg.scale_window_days)]
    older = [
        as_of - timedelta(days=offset)
        for offset in range(cfg.scale_window_days, cfg.scale_window_days * 2)
    ]
    return recent, older


def _is_scale_drift(ratio: float | None, cfg: HealthCheckConfig) -> bool:
    if ratio is None:
        return False
    return ratio >= cfg.scale_ratio or ratio <= (1.0 / cfg.scale_ratio)


def _scale_generators(
    by_date: Mapping[date, DailyRecord],
    as_of: date,
    cfg: HealthCheckConfig,
    method: str,
    names: Mapping[str, str],
    site: Site | None,
) -> list[HealthFinding]:
    recent_days, older_days = _scale_windows(as_of, cfg)
    if not _dd_comparable(by_date, recent_days, older_days, method, cfg):
        return []
    findings: list[HealthFinding] = []
    for generator_id in _generator_ids(by_date, site):
        recent = _series_on(
            by_date, recent_days, lambda rec, gid=generator_id: _generator_meter(rec, gid)
        )
        older = _series_on(
            by_date, older_days, lambda rec, gid=generator_id: _generator_meter(rec, gid)
        )
        ratio = _scale_ratio(recent, older, cfg)
        if _is_scale_drift(ratio, cfg):
            findings.append(
                _finding(
                    HealthCheckName.SCALE_DRIFT,
                    HealthSourceKind.GENERATOR,
                    generator_id,
                    _generator_name(generator_id, names, site),
                    series="carrier",
                    value=_median(recent) if recent else None,
                    typical=_median(older) if older else None,
                )
            )
    return findings


def _scale_rooms(
    room_records: Sequence[DailyRoomRecord],
    as_of: date,
    by_date: Mapping[date, DailyRecord],
    cfg: HealthCheckConfig,
    method: str,
    rooms: Mapping[str, object],
) -> list[HealthFinding]:
    recent_days, older_days = _scale_windows(as_of, cfg)
    if not _dd_comparable(by_date, recent_days, older_days, method, cfg):
        return []
    recent_set, older_set = set(recent_days), set(older_days)
    findings: list[HealthFinding] = []
    for room_id in sorted({record.room_id for record in room_records}):
        series = _room_series(room_records, room_id)
        recent = [
            value
            for day, record in series.items()
            if day in recent_set and (value := _room_value(record)) is not None
        ]
        older = [
            value
            for day, record in series.items()
            if day in older_set and (value := _room_value(record)) is not None
        ]
        ratio = _scale_ratio(recent, older, cfg)
        if _is_scale_drift(ratio, cfg):
            findings.append(
                _finding(
                    HealthCheckName.SCALE_DRIFT,
                    HealthSourceKind.ROOM,
                    room_id,
                    _room_name(room_id, rooms),
                    series="demand",
                    value=_median(recent) if recent else None,
                    typical=_median(older) if older else None,
                )
            )
    return findings


def _weather_stalled(
    by_date: Mapping[date, DailyRecord],
    as_of: date,
    cfg: HealthCheckConfig,
    weather: WeatherSourceRef,
) -> list[HealthFinding]:
    window = cfg.window_for(weather.provider)
    streak = 0
    day = as_of
    while True:
        record = by_date.get(day)
        if record is None or Flag.WEATHER_PROVISIONAL not in record.flags:
            break
        streak += 1
        day -= timedelta(days=1)
    if streak <= window:
        return []
    return [
        _finding(
            HealthCheckName.WEATHER_STALLED,
            HealthSourceKind.WEATHER,
            weather.source_id,
            weather.name,
            series="provisional",
            value=float(streak),
            typical=float(window),
        )
    ]
