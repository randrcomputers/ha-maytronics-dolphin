"""The Maytronics Dolphin (BLE) integration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .connection import (
    DolphinBleConnection,
    async_ble_periodic_release,
)
from .const import (
    CONF_ADDRESS,
    DATA_BLE_SESSION,
    DATA_CARD_SUB,
    DATA_COORDINATOR,
    DATA_JOY,
    DATA_KEEPALIVE_TASK,
    DOMAIN,
)
from .coordinator import DolphinCoordinator

_LOGGER = logging.getLogger(__name__)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if entry.state is not ConfigEntryState.LOADED:
        return
    await hass.config_entries.async_reload(entry.entry_id)


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
]


async def _async_stop_background_tasks(entry_data: dict) -> None:
    task: asyncio.Task | None = entry_data.get(DATA_KEEPALIVE_TASK)
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _async_teardown_session(entry_data: dict) -> None:
    await _async_stop_background_tasks(entry_data)
    if coord := entry_data.get(DATA_COORDINATOR):
        with suppress(Exception):
            await coord.async_shutdown()
    if session := entry_data.get(DATA_BLE_SESSION):
        session.mark_shutting_down()
        try:
            await asyncio.wait_for(session.async_disconnect(), timeout=15.0)
        except TimeoutError:
            _LOGGER.warning("Maytronics Dolphin BLE disconnect timed out during unload")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    session = DolphinBleConnection(hass, entry.data[CONF_ADDRESS], entry.entry_id)
    coordinator = DolphinCoordinator(hass, session, entry)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    release_task = hass.async_create_background_task(
        async_ble_periodic_release(hass, entry.entry_id),
        f"{DOMAIN}_ble_release_{entry.entry_id[:8]}",
    )
    entry.async_on_unload(release_task.cancel)

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_BLE_SESSION: session,
        DATA_COORDINATOR: coordinator,
        DATA_KEEPALIVE_TASK: release_task,
        DATA_JOY: {"x": 0, "y": 0},
        DATA_CARD_SUB: 4,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hass.async_create_background_task(
        coordinator.async_refresh(),
        f"{DOMAIN}_ps_state_{entry.entry_id[:8]}",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data:
        await _async_teardown_session(entry_data)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
