"""BLE transport using Home Assistant Bluetooth stack + Bleak."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_process_advertisements,
    async_rediscover_address,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .const import BLE_ADVERTISEMENT_WAIT_SECONDS

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
    # HA's Bluetooth histories and Bleak use lowercase MAC keys (same as
    # `device_registry.format_mac`). Do not use `.upper()` here or cache lookups
    # and advertisement matchers never hit.
    addr = dr.format_mac(address.strip())
    # Prefer connectable advertisements (required for GATT). Some stacks only cache
    # non-connectable beacons briefly — try both before failing.
    ble_device = bluetooth.async_ble_device_from_address(hass, addr, connectable=True)
    if ble_device is None:
        ble_device = bluetooth.async_ble_device_from_address(
            hass, addr, connectable=False
        )
    if ble_device is None:
        # Not in cache yet — common right after HA restart or if the robot has not
        # advertised recently. Ask the Bluetooth manager to wait for this MAC instead
        # of failing instantly (HA discourages BleakClient(address) without BLEDevice).
        async_rediscover_address(hass, addr)
        _LOGGER.debug(
            "Dolphin %s not in Bluetooth cache; waiting up to %ss for advertisement",
            addr,
            BLE_ADVERTISEMENT_WAIT_SECONDS,
        )
        try:
            service_info = await async_process_advertisements(
                hass,
                lambda _si: True,
                {"address": addr},
                BluetoothScanningMode.ACTIVE,
                BLE_ADVERTISEMENT_WAIT_SECONDS,
            )
        except TimeoutError:
            raise HomeAssistantError(
                f"Dolphin ({addr}) did not advertise to Home Assistant within "
                f"{BLE_ADVERTISEMENT_WAIT_SECONDS}s. "
                "Close the MyDolphin app (disconnect), move the robot or a Bluetooth "
                "proxy within range, wait for an idle advertising cycle, then check "
                "Settings → Devices & services → Bluetooth — the device should appear "
                "there before controls work. Wrong MAC also causes this."
            ) from None
        ble_device = service_info.device

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
