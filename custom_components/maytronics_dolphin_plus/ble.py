"""BLE device resolution for Plus robots (Nordic UART / alternate GATT)."""

from __future__ import annotations

import logging

from bleak.backends.device import BLEDevice
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

from .const import (
    BLE_ADVERTISEMENT_WAIT_SECONDS,
    IOT_SERVICE_UUID,
    NUS_SERVICE_UUID,
    POP_SERVICE_UUID,
    TRANSPORT_IOT_GATT,
    TRANSPORT_NUS,
    TRANSPORT_POP,
)

_LOGGER = logging.getLogger(__name__)

_INTEGRATION_VERSION = "0.1.4"

_PLUS_SERVICE_UUIDS = {
    NUS_SERVICE_UUID.lower(),
    IOT_SERVICE_UUID.lower(),
    POP_SERVICE_UUID.lower(),
}


def transport_uuids(transport: str) -> tuple[str, str, str]:
    """Return (service, write, notify) UUIDs for the selected transport."""
    from .const import (
        IOT_NOTIFY_UUID,
        IOT_WRITE_UUID,
        NUS_NOTIFY_UUID,
        NUS_WRITE_UUID,
        POP_NOTIFY_UUID,
        POP_WRITE_UUID,
    )

    if transport == TRANSPORT_POP:
        return POP_SERVICE_UUID, POP_WRITE_UUID, POP_NOTIFY_UUID
    if transport == TRANSPORT_IOT_GATT:
        return IOT_SERVICE_UUID, IOT_WRITE_UUID, IOT_NOTIFY_UUID
    return NUS_SERVICE_UUID, NUS_WRITE_UUID, NUS_NOTIFY_UUID


def _addr_hex_digits(value: str) -> str:
    return "".join(c for c in value if c in "0123456789abcdefABCDEF").lower()


def _service_uuids_lower(si: BluetoothServiceInfoBleak) -> set[str]:
    return {u.lower() for u in si.service_uuids}


def _has_plus_service(si: BluetoothServiceInfoBleak) -> bool:
    advertised = _service_uuids_lower(si)
    return bool(advertised & _PLUS_SERVICE_UUIDS)


def _matches_configured_identity(si: BluetoothServiceInfoBleak, want_hex: str) -> bool:
    """Match configured MAC to on-air BD_ADDR or BLE local name (e.g. 22554C074D50)."""
    if len(want_hex) != 12:
        return _addr_hex_digits(si.address) == want_hex
    name_hex = _addr_hex_digits(si.name or "")
    addr_hex = _addr_hex_digits(si.address)
    return want_hex == addr_hex or want_hex == name_hex


def _ble_device_from_scanners(hass: HomeAssistant, addr: str) -> BLEDevice | None:
    best: tuple[int, BLEDevice] | None = None
    for connectable in (True, False):
        entries = bluetooth.async_scanner_devices_by_address(hass, addr, connectable)
        for entry in entries:
            try:
                r = int(entry.advertisement.rssi)
            except (TypeError, ValueError):
                r = -999
            cand = entry.ble_device
            if best is None or r > best[0]:
                best = (r, cand)
    return best[1] if best else None


def _iter_discovered(
    hass: HomeAssistant, *, connectable: bool
) -> list[BluetoothServiceInfoBleak]:
    return list(
        bluetooth.async_discovered_service_info(hass, connectable=connectable)
    )


def _ble_device_from_discovered_identity(
    hass: HomeAssistant, addr: str, *, require_plus_service: bool
) -> BLEDevice | None:
    want = _addr_hex_digits(addr)
    if len(want) != 12:
        return None

    candidates: list[tuple[int, bool, BluetoothServiceInfoBleak]] = []
    for connectable in (True, False):
        for si in _iter_discovered(hass, connectable=connectable):
            if not _matches_configured_identity(si, want):
                continue
            has_plus = _has_plus_service(si)
            if require_plus_service and not has_plus:
                continue
            try:
                rssi = int(si.rssi) if si.rssi is not None else -999
            except (TypeError, ValueError):
                rssi = -999
            candidates.append((rssi, has_plus, si))

    if not candidates:
        return None

    # Prefer connectable advertisers that include a known Plus service UUID.
    candidates.sort(key=lambda row: (row[1], row[0]), reverse=True)
    best = candidates[0][2]
    if _addr_hex_digits(best.address) != want:
        _LOGGER.info(
            "Dolphin Plus v%s: resolved configured %s to on-air address %s (name=%r)",
            _INTEGRATION_VERSION,
            addr,
            best.address,
            best.name,
        )
    return best.device


def _log_nearby_candidates(hass: HomeAssistant, want_hex: str) -> None:
    """Help debug MAC / name mismatches when resolution fails."""
    hints: list[str] = []
    for connectable in (True, False):
        for si in _iter_discovered(hass, connectable=connectable):
            name = si.name or ""
            if want_hex and (
                want_hex in _addr_hex_digits(name)
                or want_hex in _addr_hex_digits(si.address)
            ):
                hints.append(
                    f"{si.address} name={name!r} connectable={connectable} "
                    f"services={list(si.service_uuids)} rssi={si.rssi}"
                )
    if hints:
        _LOGGER.warning(
            "Dolphin Plus v%s: partial BLE matches for %s: %s",
            _INTEGRATION_VERSION,
            want_hex,
            "; ".join(hints[:5]),
        )
    else:
        total = len(_iter_discovered(hass, connectable=True)) + len(
            _iter_discovered(hass, connectable=False)
        )
        _LOGGER.warning(
            "Dolphin Plus v%s: no BLE advertisers matched %s "
            "(%s entries in HA Bluetooth cache). Check Settings → "
            "Devices & services → Bluetooth.",
            _INTEGRATION_VERSION,
            want_hex,
            total,
        )


async def async_resolve_ble_device(hass: HomeAssistant, address: str) -> BLEDevice:
    """Resolve a Bleak BLEDevice from HA Bluetooth data."""
    addr = dr.format_mac(address.strip())
    want_hex = _addr_hex_digits(addr)

    _LOGGER.debug(
        "Dolphin Plus v%s: resolving BLE device for %s (hex=%s)",
        _INTEGRATION_VERSION,
        addr,
        want_hex,
    )

    ble_device = bluetooth.async_ble_device_from_address(hass, addr, connectable=True)
    if ble_device is not None:
        _LOGGER.debug("Dolphin Plus: found %s in connectable address cache", addr)
    if ble_device is None:
        ble_device = bluetooth.async_ble_device_from_address(
            hass, addr, connectable=False
        )
        if ble_device is not None:
            _LOGGER.debug("Dolphin Plus: found %s in non-connectable cache", addr)
    if ble_device is None:
        ble_device = _ble_device_from_scanners(hass, addr)
        if ble_device is not None:
            _LOGGER.debug("Dolphin Plus: found %s via live scanner cache", addr)
    if ble_device is None:
        ble_device = _ble_device_from_discovered_identity(
            hass, addr, require_plus_service=False
        )
        if ble_device is not None:
            _LOGGER.info(
                "Dolphin Plus v%s: matched %s by address/name (no service UUID required)",
                _INTEGRATION_VERSION,
                addr,
            )
    if ble_device is None:
        ble_device = _ble_device_from_discovered_identity(
            hass, addr, require_plus_service=True
        )
        if ble_device is not None:
            _LOGGER.info(
                "Dolphin Plus v%s: matched %s with Plus service UUID in advertisement",
                _INTEGRATION_VERSION,
                addr,
            )

    if ble_device is None:
        async_rediscover_address(hass, addr)
        _LOGGER.info(
            "Dolphin Plus v%s: %s not in Bluetooth cache; waiting up to %ss "
            "(match by address or local name)",
            _INTEGRATION_VERSION,
            addr,
            BLE_ADVERTISEMENT_WAIT_SECONDS,
        )

        def _advertisement_matches(si: BluetoothServiceInfoBleak) -> bool:
            return _matches_configured_identity(si, want_hex)

        service_info: BluetoothServiceInfoBleak | None = None
        wait_each = max(20, BLE_ADVERTISEMENT_WAIT_SECONDS // 2)
        for connectable in (True, False):
            try:
                service_info = await async_process_advertisements(
                    hass,
                    _advertisement_matches,
                    {"connectable": connectable},
                    BluetoothScanningMode.ACTIVE,
                    wait_each,
                )
                break
            except TimeoutError:
                _LOGGER.debug(
                    "Dolphin Plus: no advertisement for %s (connectable=%s) in %ss",
                    addr,
                    connectable,
                    wait_each,
                )
        if service_info is None:
            _log_nearby_candidates(hass, want_hex)
            raise HomeAssistantError(
                f"[v{_INTEGRATION_VERSION}] Dolphin Plus ({addr}) did not advertise "
                f"within {BLE_ADVERTISEMENT_WAIT_SECONDS}s. Close the MyDolphin Plus "
                "app, confirm the MAC in the Plus app matches Settings → Bluetooth, "
                "and check that the device appears in Home Assistant's Bluetooth "
                "integration (on-air address may differ from the configured MAC)."
            ) from None
        ble_device = service_info.device
        _LOGGER.info(
            "Dolphin Plus v%s: advertisement from %s (name=%r)",
            _INTEGRATION_VERSION,
            service_info.address,
            service_info.name,
        )

    return ble_device
