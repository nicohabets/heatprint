"""Derive Heatprint site defaults from the Home Assistant installation.

Location, time zone and country are already configured on the HA home. The
config flow must not ask for them again on first setup (CONFIG_FLOW step 1).
This module is Home Assistant-free so the mapping can be unit-tested.
"""

from __future__ import annotations

import zoneinfo
from dataclasses import dataclass

# Keep in sync with const.DEFAULT_SITE_NAME (this module must stay HA-free).
_DEFAULT_SITE_NAME = "Home"

# Unique IANA zones that map to one ISO-3166-1 alpha-2 country. Used only when
# ``hass.config.country`` is unset (older onboarding, recovered backups).
_TIMEZONE_COUNTRY: dict[str, str] = {
    "Europe/Amsterdam": "NL",
    "Europe/Brussels": "BE",
    "Europe/Berlin": "DE",
    "Europe/Paris": "FR",
    "Europe/London": "GB",
    "Europe/Dublin": "IE",
    "Europe/Vienna": "AT",
    "Europe/Zurich": "CH",
    "Europe/Rome": "IT",
    "Europe/Madrid": "ES",
    "Europe/Lisbon": "PT",
    "Europe/Copenhagen": "DK",
    "Europe/Stockholm": "SE",
    "Europe/Oslo": "NO",
    "Europe/Helsinki": "FI",
    "Europe/Warsaw": "PL",
    "Europe/Prague": "CZ",
    "Europe/Budapest": "HU",
    "Europe/Bucharest": "RO",
    "Europe/Athens": "GR",
    "Europe/Sofia": "BG",
    "Europe/Zagreb": "HR",
    "Europe/Ljubljana": "SI",
    "Europe/Bratislava": "SK",
    "Europe/Luxembourg": "LU",
    "Europe/Vaduz": "LI",
    "Europe/Andorra": "AD",
    "Europe/Monaco": "MC",
    "Europe/Malta": "MT",
    "Europe/Sarajevo": "BA",
    "Europe/Skopje": "MK",
    "Europe/Podgorica": "ME",
    "Europe/Belgrade": "RS",
    "Europe/Tirane": "AL",
    "Europe/Riga": "LV",
    "Europe/Tallinn": "EE",
    "Europe/Vilnius": "LT",
    "Europe/Kiev": "UA",
    "Europe/Kyiv": "UA",
    "Europe/Chisinau": "MD",
    "Europe/Istanbul": "TR",
    "Europe/Nicosia": "CY",
    "Atlantic/Reykjavik": "IS",
    "America/New_York": "US",
    "America/Chicago": "US",
    "America/Denver": "US",
    "America/Los_Angeles": "US",
    "America/Phoenix": "US",
    "America/Toronto": "CA",
    "America/Vancouver": "CA",
    "Australia/Sydney": "AU",
    "Australia/Melbourne": "AU",
    "Pacific/Auckland": "NZ",
}

# Inclusive bounding boxes used when the time zone is missing or ambiguous.
# Order matters: more specific regions first. NL is first because it selects KNMI.
_COUNTRY_BOXES: tuple[tuple[str, float, float, float, float], ...] = (
    ("NL", 50.75, 53.55, 3.36, 7.23),
    ("BE", 49.50, 51.51, 2.54, 6.40),
    ("LU", 49.44, 50.19, 5.73, 6.53),
    ("DE", 47.27, 55.06, 5.87, 15.04),
    ("DK", 54.56, 57.75, 8.07, 12.79),
    ("FR", 41.33, 51.09, -5.14, 9.56),
    ("GB", 49.86, 58.75, -8.18, 1.77),
    ("IE", 51.42, 55.39, -10.48, -5.99),
    ("AT", 46.37, 49.02, 9.53, 17.16),
    ("CH", 45.82, 47.81, 5.96, 10.49),
    ("IT", 36.62, 47.09, 6.63, 18.52),
    ("ES", 36.00, 43.79, -9.30, 3.32),
    ("PT", 36.96, 42.15, -9.53, -6.19),
    ("PL", 49.00, 54.84, 14.12, 24.15),
    ("CZ", 48.55, 51.06, 12.09, 18.86),
    ("SE", 55.34, 69.06, 11.11, 24.17),
    ("NO", 57.96, 71.19, 4.65, 31.17),
    ("FI", 59.81, 70.09, 20.56, 31.59),
)


@dataclass(frozen=True)
class SiteDefaults:
    """Values Heatprint copies from the Home Assistant home on first setup."""

    name: str
    latitude: float
    longitude: float
    timezone: str
    country: str


def resolve_timezone(time_zone: str | None) -> str:
    """Return a valid IANA time zone, or UTC when the value is missing or unknown."""
    candidate = (time_zone or "").strip()
    if not candidate:
        return "UTC"
    try:
        zoneinfo.ZoneInfo(candidate)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError):
        return "UTC"
    return candidate


def country_from_timezone(time_zone: str | None) -> str | None:
    """Return an ISO-2 country for a unique IANA zone, if known."""
    if not time_zone:
        return None
    return _TIMEZONE_COUNTRY.get(time_zone)


def country_from_coordinates(latitude: float, longitude: float) -> str | None:
    """Return an ISO-2 country when the point sits clearly inside a known box."""
    for country, min_lat, max_lat, min_lon, max_lon in _COUNTRY_BOXES:
        if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
            return country
    return None


def resolve_country(
    country: str | None,
    *,
    time_zone: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> str:
    """Resolve ISO-2 country: HA value, then time zone, then home coordinates.

    An empty string means "unknown": the weather step then uses the
    international (Open-Meteo) path instead of blocking on a form field.
    """
    if country and len(country.strip()) == 2:
        return country.strip().upper()
    if tz_country := country_from_timezone(time_zone):
        return tz_country
    if (
        latitude is not None
        and longitude is not None
        and (box_country := country_from_coordinates(latitude, longitude))
    ):
        return box_country
    return ""


def resolve_coordinates(
    latitude: float | None,
    longitude: float | None,
    *,
    home_latitude: float | None = None,
    home_longitude: float | None = None,
) -> tuple[float, float]:
    """Prefer HA core coordinates; fall back to zone.home when they are missing."""
    if latitude is not None and longitude is not None:
        return float(latitude), float(longitude)
    if home_latitude is not None and home_longitude is not None:
        return float(home_latitude), float(home_longitude)
    return 0.0, 0.0


def resolve_site_defaults(
    *,
    location_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    time_zone: str | None = None,
    country: str | None = None,
    home_latitude: float | None = None,
    home_longitude: float | None = None,
    home_name: str | None = None,
) -> SiteDefaults:
    """Build site defaults from HA home fields (and optional zone.home).

    The site name prefers ``zone.home``'s friendly name, then
    ``hass.config.location_name``, then ``Home``. Location / time zone /
    country are never asked on first setup.
    """
    lat, lon = resolve_coordinates(
        latitude,
        longitude,
        home_latitude=home_latitude,
        home_longitude=home_longitude,
    )
    timezone = resolve_timezone(time_zone)
    name = (home_name or "").strip() or (location_name or "").strip() or _DEFAULT_SITE_NAME
    return SiteDefaults(
        name=name,
        latitude=lat,
        longitude=lon,
        timezone=timezone,
        country=resolve_country(country, time_zone=timezone, latitude=lat, longitude=lon),
    )


def site_defaults_from_hass(hass: object) -> SiteDefaults:
    """Read ``hass.config`` and ``zone.home`` and resolve Heatprint site defaults.

    ``hass`` is typed as ``object`` so this module stays importable without
    Home Assistant installed (pytest for the core). Callers in the integration
    pass the real ``HomeAssistant`` instance.
    """
    config = getattr(hass, "config", None)
    states = getattr(hass, "states", None)
    zone = states.get("zone.home") if states is not None and hasattr(states, "get") else None
    zone_attrs = getattr(zone, "attributes", None) or {}
    zone_name = getattr(zone, "name", None) if zone is not None else None
    if not zone_name:
        zone_name = zone_attrs.get("friendly_name")
    return resolve_site_defaults(
        location_name=getattr(config, "location_name", None),
        latitude=getattr(config, "latitude", None),
        longitude=getattr(config, "longitude", None),
        time_zone=getattr(config, "time_zone", None),
        country=getattr(config, "country", None),
        home_latitude=zone_attrs.get("latitude"),
        home_longitude=zone_attrs.get("longitude"),
        home_name=zone_name,
    )
