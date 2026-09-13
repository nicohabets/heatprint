"""Register a stock Heatprint Lovelace dashboard after setup.

Uses the same Lovelace storage APIs as Home Assistant's own map dashboard
(HA 2026.9): create a storage dashboard (url_path must contain a hyphen),
then ``LovelaceStorage.async_save`` the views. When the live
``DashboardsCollection`` is not reachable, a sidebar panel is registered
directly on ``hass.data[LOVELACE_DATA]`` so the user can still open it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_NAME, CONF_SITE_ID, SUBENTRY_TYPE_GENERATOR
from .dashboard_config import (
    DASHBOARD_ICON,
    build_overview_config,
    dashboard_title,
    dashboard_url_path,
)

_LOGGER = logging.getLogger(__name__)

LOVELACE_DOMAIN = "lovelace"


def _lovelace_data(hass: HomeAssistant) -> Any | None:
    """Return the LovelaceData bag when the frontend has started."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:
        return hass.data.get(LOVELACE_DOMAIN)
    return hass.data.get(LOVELACE_DATA)


def _unwrap(func: Any) -> Any:
    """Follow ``__wrapped__`` / ``__self__`` to the collection websocket handler."""
    seen: set[int] = set()
    current = func
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        self = getattr(current, "__self__", None)
        if self is not None and hasattr(self, "storage_collection"):
            return self.storage_collection
        current = getattr(current, "__wrapped__", None)
    return None


def _dashboards_collection(hass: HomeAssistant) -> Any | None:
    """Return the live DashboardsCollection used by ``lovelace/dashboards/*``."""
    # HA stores websocket commands on hass.data["websocket_api"] (dict of handlers).
    ws_bag = hass.data.get("websocket_api")
    if isinstance(ws_bag, Mapping):
        for key, value in ws_bag.items():
            if (
                key == "lovelace/dashboards/create"
                or (isinstance(key, str) and key.endswith("dashboards/create"))
            ) and (collection := _unwrap(value)):
                return collection
        for value in ws_bag.values():
            collection = _unwrap(value)
            if collection is not None and type(collection).__name__ == "DashboardsCollection":
                return collection

    # Some HA builds keep the command table on the websocket component itself.
    commands = getattr(ws_bag, "commands", None) if ws_bag is not None else None
    if isinstance(commands, Mapping):
        handler = commands.get("lovelace/dashboards/create")
        if collection := _unwrap(handler):
            return collection
    return None


def _register_panel(hass: HomeAssistant, url_path: str, title: str, *, update: bool) -> None:
    """Show the dashboard in the sidebar (same kwargs as lovelace._register_panel)."""
    from homeassistant.components import frontend

    frontend.async_register_built_in_panel(
        hass,
        LOVELACE_DOMAIN,
        sidebar_title=title,
        sidebar_icon=DASHBOARD_ICON,
        frontend_url_path=url_path,
        require_admin=False,
        config={"mode": "storage"},
        update=update,
    )


def _attach_storage(
    hass: HomeAssistant, url_path: str, title: str, item_id: str | None = None
) -> Any:
    """Put a LovelaceStorage dashboard on LOVELACE_DATA and register the panel."""
    from homeassistant.components.frontend import async_panel_exists
    from homeassistant.components.lovelace.dashboard import LovelaceStorage

    lovelace = _lovelace_data(hass)
    if lovelace is None:
        raise HomeAssistantError("Lovelace is not loaded")
    item = {
        "id": item_id or url_path,
        "url_path": url_path,
        "title": title,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
        "mode": "storage",
    }
    store = LovelaceStorage(hass, item)
    lovelace.dashboards[url_path] = store
    _register_panel(hass, url_path, title, update=async_panel_exists(hass, url_path))
    return store


async def _save_if_needed(store: Any, config: dict[str, Any], *, recreate: bool) -> bool:
    """Write the overview when missing, or when recreate was requested."""
    from homeassistant.components.lovelace.const import ConfigNotFound

    if not recreate:
        try:
            existing = await store.async_load(False)
        except ConfigNotFound:
            existing = None
        except HomeAssistantError:
            existing = None
        if existing:
            return False
    await store.async_save(config)
    return True


def _generator_payloads(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return generator id/name pairs from subentries."""
    payloads: list[dict[str, Any]] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_GENERATOR:
            continue
        data = subentry.data
        payloads.append(
            {
                "generator_id": data.get("generator_id"),
                "name": data.get("name") or subentry.title,
            }
        )
    return payloads


async def async_ensure_overview_dashboard(
    hass: HomeAssistant, entry: ConfigEntry, *, recreate: bool = False
) -> dict[str, Any]:
    """Create or refresh the Heatprint overview dashboard for a site.

    Returns ``url_path``, ``created`` (new panel or first save) and ``updated``
    (config overwritten).
    """
    site_id = str(entry.data[CONF_SITE_ID])
    site_name = str(entry.data.get(CONF_NAME) or entry.title or site_id)
    url_path = dashboard_url_path(site_id)
    title = dashboard_title(site_name)
    config = build_overview_config(
        site_id, site_name=site_name, generators=_generator_payloads(entry)
    )

    lovelace = _lovelace_data(hass)
    if lovelace is None:
        raise HomeAssistantError("Lovelace is not loaded")

    existing = lovelace.dashboards.get(url_path)
    if existing is not None:
        wrote = await _save_if_needed(existing, config, recreate=recreate)
        return {"url_path": url_path, "created": False, "updated": wrote}

    collection = _dashboards_collection(hass)
    if collection is not None:
        try:
            item = await collection.async_create_item(
                {
                    "url_path": url_path,
                    "title": title,
                    "icon": DASHBOARD_ICON,
                    "show_in_sidebar": True,
                    "require_admin": False,
                }
            )
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.debug("DashboardsCollection create skipped: %s", err)
            store = _attach_storage(hass, url_path, title)
        else:
            store = lovelace.dashboards.get(url_path) or _attach_storage(
                hass, url_path, title, item_id=item.get("id")
            )
            await store.async_save(config)
            return {"url_path": url_path, "created": True, "updated": True}
        wrote = await _save_if_needed(store, config, recreate=True)
        return {"url_path": url_path, "created": True, "updated": wrote}

    store = _attach_storage(hass, url_path, title)
    wrote = await _save_if_needed(store, config, recreate=True)
    return {"url_path": url_path, "created": True, "updated": wrote}


async def async_setup_entry_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Best-effort dashboard create during config-entry setup (never raises)."""
    try:
        result = await async_ensure_overview_dashboard(hass, entry, recreate=False)
    except Exception:  # noqa: BLE001 - dashboard must not fail the integration
        _LOGGER.exception("Could not create the Heatprint dashboard")
        return
    _LOGGER.info(
        "Heatprint dashboard %s (%s)",
        result["url_path"],
        "created" if result["created"] else "already present",
    )
