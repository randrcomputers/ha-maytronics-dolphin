"""Power switch for Dolphin Plus local BLE."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .connection import DolphinPlusBleConnection
from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    DATA_BLE_SESSION,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import DolphinPlusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DolphinPlusCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities([DolphinPlusPowerSwitch(coordinator, entry)])


class DolphinPlusPowerSwitch(CoordinatorEntity, SwitchEntity):
    """``start_up_dolphin`` / ``shutdown_dolphin`` over Nordic UART."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Power"

    def __init__(self, coordinator: DolphinPlusCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        name = entry.data.get(CONF_NAME) or "Dolphin Plus"
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Maytronics",
            model="Dolphin Plus (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )
        self._pending_target: bool | None = None

    @property
    def assumed_state(self) -> bool:
        if self._pending_target is not None:
            return False
        return (self.coordinator.data or {}).get("power_on") is None

    @property
    def is_on(self) -> bool | None:
        if self._pending_target is not None:
            return self._pending_target
        data = self.coordinator.data or {}
        power_on = data.get("power_on")
        if isinstance(power_on, bool):
            return power_on
        return None

    def _session(self) -> DolphinPlusBleConnection:
        return self.hass.data[DOMAIN][self._entry.entry_id][DATA_BLE_SESSION]

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._pending_target = True
        self.async_write_ha_state()
        try:
            await self._session().async_startup()
            confirmed = await self.coordinator.async_refresh_until_power(True)
            if not confirmed:
                _LOGGER.warning(
                    "Power on: STARTUP sent but sm_state did not confirm ON"
                )
            else:
                await self.coordinator.async_request_refresh()
        finally:
            self._pending_target = None
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._pending_target = False
        self.async_write_ha_state()
        try:
            await self._session().async_shutdown()
            await self.coordinator.async_refresh_until_power(False)
            await self.coordinator.async_request_refresh()
        finally:
            self._pending_target = None
            self.async_write_ha_state()
