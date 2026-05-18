"""Binary sensors: cleaning activity + whether PS_State poll returned data."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_params import PSState, ps_state_cleaning_active
from .const import CONF_ADDRESS, CONF_NAME, DATA_COORDINATOR, DOMAIN
from .coordinator import DolphinCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create binary sensors."""
    coordinator: DolphinCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    async_add_entities(
        [
            DolphinCleaningActiveBinarySensor(coordinator, entry),
            DolphinPsPollOkBinarySensor(coordinator, entry),
        ],
        update_before_add=False,
    )


class _DolphinBinaryBase(CoordinatorEntity[DolphinCoordinator], BinarySensorEntity):
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


class DolphinCleaningActiveBinarySensor(_DolphinBinaryBase):
    """On when PS_State is not ``off`` (includes hold / programming / self-test)."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            key="cleaning_active",
            name="Cleaning active",
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        ps: PSState | None = data.get("ps_state") if data else None
        return ps_state_cleaning_active(ps)


class DolphinPsPollOkBinarySensor(_DolphinBinaryBase):
    """On when the last poll received a parseable ``PS_State`` (BLE path healthy)."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            key="ps_state_poll_ok",
            name="PS state data OK",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return False
        return bool(data.get("ps_poll_ok"))
