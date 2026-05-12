"""BLE transport using Home Assistant Bluetooth stack + Bleak."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import COMMAND_CHAR_UUID

_LOGGER = logging.getLogger(__name__)


def _noop_notify(_handle: int, _data: bytearray) -> None:
    """Notifications enabled for MyDolphin compatibility (payload ignored)."""


async def send_gatt_packet(
    hass: HomeAssistant,
    address: str,
    payload: bytes,
    char_uuid: str,
    *,
    pre_write_delay: float = 0.3,
    post_write_delay: float = 0.3,
) -> None:
    """Connect, notify on `char_uuid`, wait, write with response, wait, disconnect.

    Mirrors `BLEManager.writePacket` pacing. Joystick path in app uses ~50 ms;
    pass smaller delays for that case.
    """
    addr = address.upper()
    ble_device = bluetooth.async_ble_device_from_address(hass, addr, connectable=True)
    if ble_device is None:
        raise HomeAssistantError(
            "Bluetooth device not visible to Home Assistant. "
            "Confirm the MAC, range, and that a Bluetooth adapter or proxy sees this device."
        )

    try:
        async with BleakClient(ble_device, timeout=30.0) as client:
            if not client.is_connected:
                raise HomeAssistantError("Failed to connect over BLE")

            await client.start_notify(char_uuid, _noop_notify)
            await asyncio.sleep(pre_write_delay)
            await client.write_gatt_char(char_uuid, payload, response=True)
            await asyncio.sleep(post_write_delay)
            try:
                await client.stop_notify(char_uuid)
            except BleakError:
                _LOGGER.debug("stop_notify failed (ignored)", exc_info=True)
    except BleakError as err:
        raise HomeAssistantError(f"BLE error: {err}") from err
