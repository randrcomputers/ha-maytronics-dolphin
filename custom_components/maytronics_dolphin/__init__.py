"""The Maytronics Dolphin (BLE) integration."""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .connection import (
    DolphinBleConnection,
    async_ble_session_keepalive,
    async_schedule_initial_connect,
)
from .const import (
    CONF_ADDRESS,
    DATA_BLE_SESSION,
    DATA_CARD_SUB,
    DATA_COORDINATOR,
    DATA_JOY,
    DOMAIN,
)
from .coordinator import DolphinCoordinator

async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (keepalive / poll / buttons)."""
    await hass.config_entries.async_reload(entry.entry_id)


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    session = DolphinBleConnection(hass, entry.data[CONF_ADDRESS])
    coordinator = DolphinCoordinator(hass, session, entry)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_BLE_SESSION: session,
        DATA_COORDINATOR: coordinator,
        DATA_JOY: {"x": 0, "y": 0},
        DATA_CARD_SUB: 4,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    keepalive = hass.async_create_background_task(
        async_ble_session_keepalive(hass, entry.entry_id),
        f"{DOMAIN}_ble_keepalive_{entry.entry_id[:8]}",
    )
    entry.async_on_unload(keepalive.cancel)

    hass.async_create_background_task(
        async_schedule_initial_connect(hass, entry.entry_id),
        f"{DOMAIN}_initial_ble_{entry.entry_id[:8]}",
    )
    hass.async_create_background_task(
        coordinator.async_refresh(),
        f"{DOMAIN}_ps_state_{entry.entry_id[:8]}",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if entry_data:
            if coord := entry_data.get(DATA_COORDINATOR):
                await coord.async_shutdown()
            if session := entry_data.get(DATA_BLE_SESSION):
                await session.async_disconnect()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
