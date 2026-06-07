"""Domain services for built-in cleaner schedule."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DATA_SCHEDULE, DOMAIN
from .schedule import DolphinScheduleManager

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_RUN_TIMED = "run_timed"

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("enabled"): cv.boolean,
        vol.Optional("days"): cv.string,
        vol.Optional("run1_time"): cv.string,
        vol.Optional("run1_duration_minutes"): vol.All(cv.positive_int, vol.In([60, 120])),
        vol.Optional("run2_enabled"): cv.boolean,
        vol.Optional("run2_time"): cv.string,
        vol.Optional("run2_duration_minutes"): vol.All(cv.positive_int, vol.In([60, 120])),
    }
)

RUN_TIMED_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("duration_minutes"): vol.All(cv.positive_int, vol.In([60, 120])),
    }
)


def _entry_for_device(hass: HomeAssistant, device_id: str) -> ConfigEntry | None:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, entry_id in device.identifiers:
        if domain == DOMAIN:
            return hass.config_entries.async_get_entry(entry_id)
    return None


def _manager_for_call(hass: HomeAssistant, call: ServiceCall) -> DolphinScheduleManager | None:
    entry = _entry_for_device(hass, call.data["device_id"])
    if entry is None:
        _LOGGER.warning("set_schedule/run_timed: unknown device_id %s", call.data["device_id"])
        return None
    bucket = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not bucket:
        return None
    return bucket.get(DATA_SCHEDULE)


async def _async_set_schedule(call: ServiceCall) -> None:
    manager = _manager_for_call(call.hass, call)
    if manager is None:
        return
    data = dict(call.data)
    data.pop("device_id", None)
    await manager.async_update(**data)


async def _async_run_timed(call: ServiceCall) -> None:
    manager = _manager_for_call(call.hass, call)
    if manager is None:
        return
    await manager.async_run_timed(int(call.data["duration_minutes"]))


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register schedule services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        _async_set_schedule,
        schema=SET_SCHEDULE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_TIMED,
        _async_run_timed,
        schema=RUN_TIMED_SCHEMA,
    )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Remove services when last config entry unloads."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
    if hass.services.has_service(DOMAIN, SERVICE_RUN_TIMED):
        hass.services.async_remove(DOMAIN, SERVICE_RUN_TIMED)
