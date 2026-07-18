"""Maytronics Dolphin Plus — local BLE (MyDolphin Plus app protocol)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .connection import DolphinPlusBleConnection, async_ble_periodic_release
from .const import (
    CONF_ADDRESS,
    CONF_PROFILE,
    CONF_TRANSPORT,
    DATA_BLE_SESSION,
    DATA_COORDINATOR,
    DATA_KEEPALIVE_TASK,
    DEFAULT_PROFILE,
    DEFAULT_TRANSPORT,
    DOMAIN,
)
from .coordinator import DolphinPlusCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if entry.state is not ConfigEntryState.LOADED:
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    profile = entry.data.get(CONF_PROFILE, DEFAULT_PROFILE)
    transport = entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
    session = DolphinPlusBleConnection(
        hass,
        entry.data[CONF_ADDRESS],
        entry.entry_id,
        profile=profile,
        transport=transport,
    )
    coordinator = DolphinPlusCoordinator(hass, session, entry)
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
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.async_create_background_task(
        coordinator.async_refresh(),
        f"{DOMAIN}_status_{entry.entry_id[:8]}",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data:
        task: asyncio.Task | None = entry_data.get(DATA_KEEPALIVE_TASK)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if coord := entry_data.get(DATA_COORDINATOR):
            with suppress(Exception):
                await coord.async_shutdown()
        if session := entry_data.get(DATA_BLE_SESSION):
            session.mark_shutting_down()
            try:
                await asyncio.wait_for(session.async_disconnect(), timeout=15.0)
            except TimeoutError:
                _LOGGER.warning("Dolphin Plus BLE disconnect timed out during unload")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
