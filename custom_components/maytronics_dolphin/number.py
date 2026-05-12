"""Joystick axis numbers (stored for Send joystick button)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ADDRESS, CONF_NAME, DATA_JOY, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Joystick X/Y."""
    async_add_entities(
        [
            DolphinJoystickAxisNumber(entry, "joystick_x", "Joystick X", "x"),
            DolphinJoystickAxisNumber(entry, "joystick_y", "Joystick Y", "y"),
        ],
        update_before_add=False,
    )


class DolphinJoystickAxisNumber(NumberEntity):
    """Axis value -128..127 (MyDolphin `sendJoystickCommand` range style)."""

    _attr_has_entity_name = True
    _attr_native_min_value = -128
    _attr_native_max_value = 127
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_value = 0

    def __init__(
        self, entry: ConfigEntry, key: str, title: str, axis: str
    ) -> None:
        super().__init__()
        self._entry = entry
        self._axis = axis
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        v = int(
            self.hass.data[DOMAIN][self._entry.entry_id][DATA_JOY][self._axis]
        )
        self._attr_native_value = v

    async def async_set_native_value(self, value: float) -> None:
        v = int(value)
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_JOY][self._axis] = v
        self._attr_native_value = v
        self.async_write_ha_state()
