"""Card self-test + PS cycle-time selectors."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_params import (
    cycle_time_label,
    cycle_time_minutes_from_label,
)
from .connection import DolphinBleConnection
from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    DATA_BLE_SESSION,
    DATA_CARD_SUB,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import DolphinCoordinator

_LOGGER = logging.getLogger(__name__)

OPTIONS: list[tuple[str, int]] = [
    ("vdd", 1),
    ("tilt", 2),
    ("impeller", 3),
    ("drive", 4),
    ("gyro", 5),
    ("servo", 6),
    ("servo_calib", 7),
]

CYCLE_TIME_OPTIONS = ["1 hour", "2 hours"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Card test preset + cycle time."""
    coordinator: DolphinCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        [
            DolphinCardTestSelect(entry),
            DolphinCycleTimeSelect(coordinator, entry),
        ],
        update_before_add=False,
    )


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


class DolphinCycleTimeSelect(CoordinatorEntity, SelectEntity):
    """PS cycle length — APK ``BLEManager.setCicleTime`` (1h floor / 2h floor+wall)."""

    _attr_has_entity_name = True
    _attr_name = "Cycle time"
    _attr_options = CYCLE_TIME_OPTIONS

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        SelectEntity.__init__(self)
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        name = entry.data.get(CONF_NAME) or "Dolphin"
        self._attr_unique_id = f"{entry.entry_id}_cycle_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Maytronics",
            model="Dolphin (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )

    @property
    def current_option(self) -> str | None:
        minutes = (self.coordinator.data or {}).get("cycle_time_minutes")
        label = cycle_time_label(minutes if isinstance(minutes, int) else None)
        if label in CYCLE_TIME_OPTIONS:
            return label
        # Unknown/other PS values: prefer nearest of the two UI options.
        if isinstance(minutes, int):
            if minutes <= 90:
                return "1 hour"
            return "2 hours"
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in CYCLE_TIME_OPTIONS:
            return
        minutes = cycle_time_minutes_from_label(option)
        session: DolphinBleConnection = self.hass.data[DOMAIN][self._entry.entry_id][
            DATA_BLE_SESSION
        ]
        try:
            await session.async_write_cycle_time_minutes(minutes)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Maytronics Dolphin cycle time write failed: %s", err)
            raise
        # Optimistic + refresh so Power countdown / select stay in sync.
        prev = dict(self.coordinator.data or {})
        prev["cycle_time_minutes"] = minutes
        prev["cycle_time_poll_ok"] = True
        self.coordinator.async_set_updated_data(prev)
        await self.coordinator.async_force_full_refresh()
