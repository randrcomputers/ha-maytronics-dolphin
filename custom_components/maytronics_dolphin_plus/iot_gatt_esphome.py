"""Send IoT GATT commands via an ESPHome proxy BLE server (pool-area ESP32)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from homeassistant.components.esphome import DOMAIN as ESPHOME_DOMAIN
from homeassistant.helpers import device_registry as dr

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

ESPHOME_IOT_NOTIFY_ACTION = "dolphin_iot_notify"
_SERVICE_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _esphome_service_slug(name: str) -> str:
    slug = name.strip().lower().replace("-", "_").replace(" ", "_")
    return _SERVICE_SLUG_RE.sub("", slug)


def esphome_notify_service_name(node_name: str) -> str:
    """HA service name under the ``esphome`` domain (without domain prefix)."""
    return f"{_esphome_service_slug(node_name)}_{ESPHOME_IOT_NOTIFY_ACTION}"


def _list_esphome_notify_services(hass: HomeAssistant) -> list[str]:
    return [
        name
        for name in hass.services.async_services().get(ESPHOME_DOMAIN, {})
        if name.endswith(f"_{ESPHOME_IOT_NOTIFY_ACTION}")
    ]


def async_resolve_esphome_notify_service(
    hass: HomeAssistant, device_id: str
) -> str | None:
    """Map an ESPHome device registry id to ``dolphin_iot_notify`` service name."""
    if ESPHOME_DOMAIN not in hass.config.components:
        return None

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    if device is None:
        return None

    notify_services = _list_esphome_notify_services(hass)
    if not notify_services:
        return None

    for config_entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != ESPHOME_DOMAIN:
            continue
        candidates = {
            _esphome_service_slug(str(entry.title or "")),
            _esphome_service_slug(str(entry.data.get("name", ""))),
        }
        for slug in candidates:
            if not slug:
                continue
            service = f"{slug}_{ESPHOME_IOT_NOTIFY_ACTION}"
            if service in notify_services:
                return service
        for service in notify_services:
            if any(slug and slug in service for slug in candidates if slug):
                return service

    if len(notify_services) == 1:
        return notify_services[0]

    _LOGGER.debug(
        "Dolphin Plus: could not match ESPHome device %s to a %s service "
        "(available: %s)",
        device_id,
        ESPHOME_IOT_NOTIFY_ACTION,
        notify_services,
    )
    return None


async def async_esphome_iot_notify(
    hass: HomeAssistant, service_name: str, payload: bytes
) -> bool:
    """Invoke ``esphome.<node>_dolphin_iot_notify`` with frame bytes."""
    if not payload:
        return False
    data = {"payload": [b & 0xFF for b in payload]}
    await hass.services.async_call(
        ESPHOME_DOMAIN,
        service_name,
        data,
        blocking=True,
    )
    _LOGGER.info(
        "Dolphin Plus: ESPHome IoT notify sent via esphome.%s (%d bytes): %s",
        service_name,
        len(payload),
        payload.hex(),
    )
    return True
