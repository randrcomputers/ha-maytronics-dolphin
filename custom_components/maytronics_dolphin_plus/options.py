"""Integration options."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import (
    BLE_SESSION_KEEPALIVE_INTERVAL_SEC,
    DEFAULT_IOT_GATT_BACKEND,
    IOT_GATT_BACKEND_AUTO,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_ESPHOME_DEVICE,
    OPT_IOT_GATT_BACKEND,
    OPT_STATE_POLL_SEC,
    STATE_POLL_INTERVAL_SEC,
)


def get_integration_options(entry: ConfigEntry) -> dict[str, int | str | None]:
    data = entry.options
    esphome_device = data.get(OPT_ESPHOME_DEVICE)
    return {
        OPT_BLE_KEEPALIVE_SEC: int(
            data.get(OPT_BLE_KEEPALIVE_SEC, BLE_SESSION_KEEPALIVE_INTERVAL_SEC)
        ),
        OPT_STATE_POLL_SEC: int(
            data.get(OPT_STATE_POLL_SEC, STATE_POLL_INTERVAL_SEC)
        ),
        OPT_IOT_GATT_BACKEND: str(
            data.get(OPT_IOT_GATT_BACKEND, DEFAULT_IOT_GATT_BACKEND)
        ),
        OPT_ESPHOME_DEVICE: esphome_device if esphome_device else None,
    }
