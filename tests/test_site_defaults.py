"""HA home defaults for the Heatprint config flow (no Home Assistant import)."""

from __future__ import annotations

from types import SimpleNamespace

from site_defaults import (
    country_from_coordinates,
    country_from_timezone,
    resolve_country,
    resolve_site_defaults,
    resolve_timezone,
    site_defaults_from_hass,
)


def test_timezone_from_ha_and_invalid_fallback() -> None:
    assert resolve_timezone("Europe/Amsterdam") == "Europe/Amsterdam"
    assert resolve_timezone("Not/AZone") == "UTC"
    assert resolve_timezone("  ") == "UTC"
    assert resolve_timezone(None) == "UTC"


def test_country_prefers_ha_then_timezone_then_coordinates() -> None:
    assert resolve_country("nl") == "NL"
    assert resolve_country(None, time_zone="Europe/Amsterdam") == "NL"
    assert resolve_country(None, time_zone="Europe/Berlin") == "DE"
    assert resolve_country(None, latitude=50.85, longitude=5.69) == "NL"
    assert resolve_country(None, time_zone="UTC", latitude=-33.87, longitude=151.21) == ""


def test_country_from_timezone_and_boxes() -> None:
    assert country_from_timezone("Europe/Amsterdam") == "NL"
    assert country_from_timezone("Pacific/Honolulu") is None
    assert country_from_coordinates(52.37, 4.90) == "NL"
    assert country_from_coordinates(48.86, 2.35) == "FR"
    assert country_from_coordinates(0.0, 0.0) is None


def test_resolve_site_defaults_uses_ha_home() -> None:
    defaults = resolve_site_defaults(
        location_name="Heerlen",
        latitude=50.888,
        longitude=5.979,
        time_zone="Europe/Amsterdam",
        country="NL",
    )
    assert defaults.name == "Heerlen"
    assert defaults.latitude == 50.888
    assert defaults.longitude == 5.979
    assert defaults.timezone == "Europe/Amsterdam"
    assert defaults.country == "NL"


def test_resolve_site_defaults_derives_country_and_name() -> None:
    defaults = resolve_site_defaults(
        location_name=None,
        latitude=50.888,
        longitude=5.979,
        time_zone="Europe/Amsterdam",
        country=None,
    )
    assert defaults.name == "Home"
    assert defaults.country == "NL"
    assert defaults.timezone == "Europe/Amsterdam"


def test_zone_home_fills_missing_core_coordinates() -> None:
    defaults = resolve_site_defaults(
        location_name="Home",
        latitude=None,
        longitude=None,
        time_zone="Europe/Amsterdam",
        country=None,
        home_latitude=51.44,
        home_longitude=5.48,
    )
    assert defaults.latitude == 51.44
    assert defaults.longitude == 5.48
    assert defaults.country == "NL"


def test_site_defaults_from_hass_reads_config_and_zone() -> None:
    hass = SimpleNamespace(
        config=SimpleNamespace(
            location_name="Maastricht",
            latitude=50.85,
            longitude=5.69,
            time_zone="Europe/Amsterdam",
            country=None,
        ),
        states=SimpleNamespace(
            get=lambda _entity_id: SimpleNamespace(attributes={"latitude": 1.0, "longitude": 2.0})
        ),
    )
    defaults = site_defaults_from_hass(hass)
    assert defaults.name == "Maastricht"
    assert defaults.latitude == 50.85
    assert defaults.longitude == 5.69
    assert defaults.country == "NL"
