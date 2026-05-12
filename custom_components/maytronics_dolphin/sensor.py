"""Sensors: cleaner state from ``PS_State`` + diagnostic GATT reads."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_params import PSState, ps_state_to_str
from .const import CONF_ADDRESS, CONF_NAME, DATA_COORDINATOR, DOMAIN
from .coordinator import DolphinCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors."""
    coordinator: DolphinCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        [
            DolphinCleanerStateSensor(coordinator, entry),
            DolphinStatusRawSensor(coordinator, entry, "fffc"),
            DolphinStatusRawSensor(coordinator, entry, "fffd"),
        ],
        update_before_add=False,
    )


class _DolphinDiagSensorBase(CoordinatorEntity[DolphinCoordinator], SensorEntity):
    """Shared device info for coordinator-backed sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DolphinCoordinator,
        entry: ConfigEntry,
        *,
        key: str,
        name: str,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        dev_name = entry.data.get(CONF_NAME) or "Dolphin"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        if entity_category is not None:
            self._attr_entity_category = entity_category
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=dev_name,
            manufacturer="Maytronics",
            model="Dolphin (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )


class DolphinCleanerStateSensor(_DolphinDiagSensorBase):
    """Text state from ``ConfigParamsRead`` PS_State (same poll as Power sync)."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            key="cleaner_state",
            name="Cleaner state",
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        ps: PSState | None = data.get("ps_state") if data else None
        return ps_state_to_str(ps)


class DolphinStatusRawSensor(_DolphinDiagSensorBase):
    """Hex dump of optional GATT read on ``fffc`` / ``fffd`` (diagnostic)."""

    def __init__(
        self,
        coordinator: DolphinCoordinator,
        entry: ConfigEntry,
        which: str,
    ) -> None:
        key = f"status_raw_{which}"
        title = f"Status raw ({which})"
        super().__init__(
            coordinator,
            entry,
            key=key,
            name=title,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._which = which

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if not data:
            return None
        if self._which == "fffc":
            return data.get("status_fffc_hex")
        return data.get("internal_fffd_hex")
