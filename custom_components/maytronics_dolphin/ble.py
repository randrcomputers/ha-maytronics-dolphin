"""BLE transport using Home Assistant Bluetooth stack + Bleak."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_process_advertisements,
    async_rediscover_address,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .const import BLE_ADVERTISEMENT_WAIT_SECONDS, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

# Texas Instruments — common on Maytronics BLE modules; narrows FFF0-only matches.
_MANUFACTURER_ID_TEXAS_INSTRUMENTS = 0x000D


def _noop_notify(_handle: int, _data: bytearray) -> None:
    """Notifications enabled for MyDolphin compatibility (payload ignored)."""


def _addr_hex_digits(value: str) -> str:
    """Normalize to lowercase hex digits only (12 chars for a BD_ADDR)."""
    return "".join(c for c in value if c in "0123456789abcdefABCDEF").lower()


def _service_uuids_lower(si: BluetoothServiceInfoBleak) -> set[str]:
    return {u.lower() for u in si.service_uuids}


def _has_mydolphin_service(si: BluetoothServiceInfoBleak) -> bool:
    return SERVICE_UUID.lower() in _service_uuids_lower(si)


def _ble_device_from_scanners(hass: HomeAssistant, addr: str) -> BLEDevice | None:
    """Live per-scanner caches — sometimes populated when merged history is empty."""
    best: tuple[int, BLEDevice] | None = None
    for connectable in (True, False):
        entries = bluetooth.async_scanner_devices_by_address(hass, addr, connectable)
        for entry in entries:
            rssi = entry.advertisement.rssi
            try:
                r = int(rssi)
            except (TypeError, ValueError):
                r = -999
            cand = entry.ble_device
            if best is None or r > best[0]:
                best = (r, cand)
    return best[1] if best else None


def _ble_device_from_discovered_identity(hass: HomeAssistant, addr: str) -> BLEDevice | None:
    """Match config MAC to an advertiser by BD_ADDR *or* by local name (e.g. 22554C074D50).

    Many Dolphins advertise a random-looking BD_ADDR (e.g. e0:ff:…) while the
    shortened local name carries the TI-style identity bytes — so the user may
    configure either address but HA history keys only the on-air address.
    """
    want = _addr_hex_digits(addr)
    if len(want) != 12:
        return None

    candidates: list[tuple[bool, int, BluetoothServiceInfoBleak]] = []
    for si in bluetooth.async_discovered_service_info(hass, connectable=True):
        if not _has_mydolphin_service(si):
            continue
        name_d = _addr_hex_digits(si.name or "")
        addr_d = _addr_hex_digits(si.address)
        if want != name_d and want != addr_d:
            continue
        has_ti = _MANUFACTURER_ID_TEXAS_INSTRUMENTS in si.manufacturer_data
        try:
            rssi = int(si.rssi) if si.rssi is not None else -999
        except (TypeError, ValueError):
            rssi = -999
        candidates.append((has_ti, rssi, si))

    if not candidates:
        return None

    ti_only = [row for row in candidates if row[0]]
    pool = ti_only if ti_only else candidates
    pool.sort(key=lambda row: row[1], reverse=True)
    best = pool[0][2]
    if _addr_hex_digits(best.address) != want and want == _addr_hex_digits(best.name or ""):
        _LOGGER.debug(
            "Resolved configured %s to on-air address %s via name + FFF0 service",
            addr,
            best.address,
        )
    return best.device


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
    # HA / BlueZ use lowercase MAC keys (same as `device_registry.format_mac`).
    addr = dr.format_mac(address.strip())

    ble_device = bluetooth.async_ble_device_from_address(hass, addr, connectable=True)
    if ble_device is None:
        ble_device = bluetooth.async_ble_device_from_address(
            hass, addr, connectable=False
        )
    if ble_device is None:
        ble_device = _ble_device_from_scanners(hass, addr)
    if ble_device is None:
        ble_device = _ble_device_from_discovered_identity(hass, addr)

    if ble_device is None:
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
