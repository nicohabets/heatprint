"""Device registry UX: branded names and safe area / rename alignment."""

from __future__ import annotations

from pathlib import Path

from device_registry_ux import (
    ChildDeviceSpec,
    DeviceSnapshot,
    branded_device_name,
    device_identifier,
    is_legacy_auto_device_name,
    plan_child_device_alignment,
)

REPO = Path(__file__).resolve().parents[1]
SENSOR = REPO / "custom_components" / "heatprint" / "sensor.py"


def test_branded_device_name_uses_integration_not_site() -> None:
    assert branded_device_name("Slaapkamer") == "Heatprint Slaapkamer"
    assert branded_device_name("  Living ") == "Heatprint Living"
    assert branded_device_name("") == "Heatprint"
    assert branded_device_name(None) == "Heatprint"
    assert "Thuis" not in branded_device_name("Slaapkamer")


def test_legacy_auto_name_is_site_plus_part() -> None:
    assert is_legacy_auto_device_name("Thuis Slaapkamer", "Thuis", "Slaapkamer") is True
    assert is_legacy_auto_device_name("Heatprint Slaapkamer", "Thuis", "Slaapkamer") is False
    assert is_legacy_auto_device_name("Slaapkamer voor", "Thuis", "Slaapkamer") is False
    assert is_legacy_auto_device_name(None, "Thuis", "Slaapkamer") is False
    assert is_legacy_auto_device_name("Thuis Slaapkamer", "", "Slaapkamer") is False


def test_plan_fills_empty_area_and_clears_legacy_name() -> None:
    plan = plan_child_device_alignment(
        entry_id="abc",
        site_name="Thuis",
        children=(
            ChildDeviceSpec("slaapkamer", "Slaapkamer", "area_sleep"),
            ChildDeviceSpec("living", "Living", "area_living"),
            ChildDeviceSpec("boiler", "Gasketel", None),
        ),
        devices=(
            DeviceSnapshot(
                "dev-sleep",
                device_identifier("abc", "slaapkamer"),
                None,
                "Thuis Slaapkamer",
            ),
            DeviceSnapshot(
                "dev-living",
                device_identifier("abc", "living"),
                "area_other",
                "Woonkamer Nico",
            ),
            DeviceSnapshot(
                "dev-boiler",
                device_identifier("abc", "boiler"),
                None,
                "Thuis Gasketel",
            ),
        ),
    )
    by_id = {op.device_id: op for op in plan}
    assert by_id["dev-sleep"].area_id == "area_sleep"
    assert by_id["dev-sleep"].clear_name_by_user is True
    assert "dev-living" not in by_id
    assert by_id["dev-boiler"].area_id is None
    assert by_id["dev-boiler"].clear_name_by_user is True


def test_plan_skips_unknown_and_already_aligned_devices() -> None:
    plan = plan_child_device_alignment(
        entry_id="abc",
        site_name="Thuis",
        children=(ChildDeviceSpec("slaapkamer", "Slaapkamer", "area_sleep"),),
        devices=(
            DeviceSnapshot(
                "dev-sleep",
                device_identifier("abc", "slaapkamer"),
                "area_sleep",
                "Heatprint Slaapkamer",
            ),
        ),
    )
    assert plan == ()


def test_sensor_device_info_uses_brand_and_suggested_area() -> None:
    source = SENSOR.read_text(encoding="utf-8")
    assert 'f"{coordinator.site_name} {room.name}"' not in source
    assert 'f"{coordinator.site_name} {generator.name}"' not in source
    assert "branded_device_name(room.name)" in source
    assert "branded_device_name(generator.name)" in source
    assert '"suggested_area"' in source
    assert "suggested_area_name" in source
