"""Sensors: cleaner state from ``PS_State`` + diagnostic GATT reads."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_params import CleanMode, PSState, clean_mode_to_str, ps_state_to_str
from .status_params import CleaningSurface, WorkingStatus
from .const import CONF_ADDRESS, CONF_NAME, DATA_COORDINATOR, DATA_SCHEDULE, DOMAIN
from .coordinator import DolphinCoordinator
from .schedule import DolphinScheduleManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors."""
    coordinator: DolphinCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]
    schedule: DolphinScheduleManager = hass.data[DOMAIN][entry.entry_id][
        DATA_SCHEDULE
    ]
    async_add_entities(
        [
            DolphinCleanerStateSensor(coordinator, entry),
            DolphinCleanProgramSensor(coordinator, entry),
            DolphinCleaningSurfaceSensor(coordinator, entry),
            DolphinWorkingStatusSensor(coordinator, entry),
            DolphinScheduleSensor(schedule, entry),
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


class DolphinCleanProgramSensor(_DolphinDiagSensorBase):
    """Selected clean program from ``Working_Clean_Mode`` (ConfigParamsRead cmd **5**)."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            key="clean_program",
            name="Clean program",
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        mode: CleanMode | None = data.get("clean_mode") if data else None
        return clean_mode_to_str(mode)


class DolphinWorkingStatusSensor(_DolphinDiagSensorBase):
    """``GetStatusRead$WorkingStatus`` — at_work vs finished (for pool card / automations)."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            key="working_status",
            name="Working status",
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        working: WorkingStatus | None = data.get("working_status") if data else None
        if working is not None:
            return str(working)
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | None]:
        data = self.coordinator.data or {}
        raw = data.get("working_status_raw")
        return {
            "working_status_raw": str(raw) if raw is not None else None,
            "working_status_held": bool(data.get("working_status_held")),
        }


class DolphinCleaningSurfaceSensor(_DolphinDiagSensorBase):
    """Best-effort floor/wall/waterline from ``InternalParamsRead`` + clean program."""

    def __init__(self, coordinator: DolphinCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            key="cleaning_surface",
            name="Cleaning surface",
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        surface: CleaningSurface | None = (
            data.get("cleaning_surface") if data else None
        )
        if surface is None:
            return "unknown"
        return str(surface)

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        data = self.coordinator.data or {}
        snap = data.get("internal_snapshot")
        attrs: dict[str, str | int | None] = {
            "working_status": (
                str(data["working_status"]) if data.get("working_status") else None
            ),
            "internal_poll_ok": data.get("internal_poll_ok"),
        }
        if snap is not None:
            attrs["phase_byte"] = snap.phase_byte
            attrs["motor_aux_byte"] = snap.motor_aux
            attrs["climb_every_byte"] = snap.climb_every
            attrs["clean_mode_byte"] = snap.clean_mode_byte
        return attrs


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


class DolphinScheduleSensor(SensorEntity):
    """Stored daily schedule (read by Pool Cleaner Card; no YAML helpers required)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, manager: DolphinScheduleManager, entry: ConfigEntry
    ) -> None:
        self._manager = manager
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        dev_name = entry.data.get(CONF_NAME) or "Dolphin"
        self._attr_unique_id = f"{entry.entry_id}_schedule"
        self._attr_name = "Cleaner schedule"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=dev_name,
            manufacturer="Maytronics",
            model="Dolphin (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )
        manager.add_listener(self._schedule_changed)

    @callback
    def _schedule_changed(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return "on" if self._manager.config.enabled else "off"

    @property
    def extra_state_attributes(self) -> dict[str, bool | int | str]:
        return self._manager.config.as_attributes()
