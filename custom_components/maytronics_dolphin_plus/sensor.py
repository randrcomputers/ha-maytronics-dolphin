"""Sensors for Dolphin Plus BLE status."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, CONF_NAME, DATA_COORDINATOR, DOMAIN
from .coordinator import DolphinPlusCoordinator
from .protocol import PowerState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DolphinPlusCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        [
            DolphinPlusSmStateSensor(coordinator, entry),
            DolphinPlusMuStateSensor(coordinator, entry),
            DolphinPlusCleaningModeSensor(coordinator, entry),
        ]
    )


class _DolphinPlusSensorBase(CoordinatorEntity[DolphinPlusCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DolphinPlusCoordinator,
        entry: ConfigEntry,
        *,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        dev_name = entry.data.get(CONF_NAME) or "Dolphin Plus"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=dev_name,
            manufacturer="Maytronics",
            model="Dolphin Plus (BLE)",
            connections={
                (dr.CONNECTION_BLUETOOTH, dr.format_mac(entry.data[CONF_ADDRESS]))
            },
        )


class DolphinPlusSmStateSensor(_DolphinPlusSensorBase):
    """Raw ``sm_state`` from ``system_status`` (0 ≈ off)."""

    def __init__(self, coordinator: DolphinPlusCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, key="sm_state", name="SM state")

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        if not data.get("poll_ok"):
            return None
        sm = data.get("sm_state")
        if sm is None:
            return None
        power = data.get("power_state")
        if power == PowerState.ON:
            return f"on ({sm})"
        if power == PowerState.OFF:
            return f"off ({sm})"
        return str(sm)


class DolphinPlusMuStateSensor(_DolphinPlusSensorBase):
    def __init__(self, coordinator: DolphinPlusCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, key="mu_state", name="MU state")

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data or {}
        if not data.get("poll_ok"):
            return None
        mu = data.get("mu_state")
        return int(mu) if isinstance(mu, int) else None


class DolphinPlusCleaningModeSensor(_DolphinPlusSensorBase):
    def __init__(self, coordinator: DolphinPlusCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, key="cleaning_mode", name="Cleaning mode"
        )

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data or {}
        if not data.get("poll_ok"):
            return None
        mode = data.get("cleaning_mode")
        return int(mode) if isinstance(mode, int) else None
