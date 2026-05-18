"""Card self-test subcommand selector (1..7)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ADDRESS, CONF_NAME, DATA_CARD_SUB, DOMAIN

OPTIONS: list[tuple[str, int]] = [
    ("vdd", 1),
    ("tilt", 2),
    ("impeller", 3),
    ("drive", 4),
    ("gyro", 5),
    ("servo", 6),
    ("servo_calib", 7),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Card test preset."""
    async_add_entities([DolphinCardTestSelect(entry)], update_before_add=False)


class DolphinCardTestSelect(SelectEntity):
    """Select which `Card_Test` sub-byte to send with *Run card test*."""

    _attr_has_entity_name = True
    _attr_name = "Card test type"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__()
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        name = entry.data.get(CONF_NAME) or "Dolphin"
        self._attr_unique_id = f"{entry.entry_id}_card_test_type"
        self._attr_options = [o[0] for o in OPTIONS]
        self._map = {o[0]: o[1] for o in OPTIONS}
        self._attr_current_option = "drive"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Maytronics",
            model="Dolphin (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_CARD_SUB] = self._map[
            self._attr_current_option
        ]

    async def async_select_option(self, option: str) -> None:
        if option not in self._map:
            return
        self._attr_current_option = option
        self.hass.data[DOMAIN][self._entry.entry_id][DATA_CARD_SUB] = self._map[
            option
        ]
        self.async_write_ha_state()
