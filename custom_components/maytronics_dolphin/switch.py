"""Power + Autoclean switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .connection import DolphinBleConnection
from .config_params import ps_state_implies_power_on
from .const import (
    COMMAND_CHAR_UUID,
    CONF_ADDRESS,
    CONF_NAME,
    DATA_BLE_SESSION,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import DolphinCoordinator
from .protocol import BTCommandType, build_bt_command_19

SWITCH_POWER = "power"
SWITCH_AUTOCLEAN = "autoclean"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create switches."""
    coordinator: DolphinCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        [
            DolphinPowerSwitch(coordinator, entry),
            DolphinAutocleanSwitch(entry),
        ],
        update_before_add=False,
    )


class _DolphinBaseSwitch(SwitchEntity):
    """Shared device info."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_available = True

    def __init__(self, entry: ConfigEntry, key: str, title: str) -> None:
        super().__init__()
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        name = entry.data.get(CONF_NAME) or "Dolphin"
        self._attr_name = title
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Maytronics",
            model="Dolphin (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )
        self._attr_is_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    async def _send(self, payload: bytes) -> None:
        session: DolphinBleConnection = self.hass.data[DOMAIN][self._entry.entry_id][
            DATA_BLE_SESSION
        ]
        await session.async_send_gatt_packet(payload, COMMAND_CHAR_UUID)


class DolphinPowerSwitch(CoordinatorEntity, _DolphinBaseSwitch):
    """19-byte FFF8 power commands + ``ConfigParamsRead`` PS_State sync (``fffa``)."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        _DolphinBaseSwitch.__init__(self, entry, SWITCH_POWER, "Power")

    @property
    def assumed_state(self) -> bool:
        ps = (self.coordinator.data or {}).get("ps_state")
        return ps is None

    @property
    def is_on(self) -> bool | None:
        ps = (self.coordinator.data or {}).get("ps_state") if self.coordinator.data else None
        inferred = ps_state_implies_power_on(ps)
        if inferred is not None:
            return inferred
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(build_bt_command_19(BTCommandType.STARTUP))
        self._attr_is_on = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(build_bt_command_19(BTCommandType.SHUTDOWN))
        self._attr_is_on = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._attr_is_on = None


class DolphinAutocleanSwitch(_DolphinBaseSwitch):
    """Autoclean enable (19-byte `BTCommand` frame)."""

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, SWITCH_AUTOCLEAN, "Autoclean")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(
            build_bt_command_19(
                BTCommandType.AUTOCLEAN_ENABLE, autoclean_on=True
            )
        )
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(
            build_bt_command_19(
                BTCommandType.AUTOCLEAN_ENABLE, autoclean_on=False
            )
        )
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._attr_is_on = None
