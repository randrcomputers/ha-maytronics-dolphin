"""Discover Plus BLE write/notify characteristics after GATT connect."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bleak import BleakClient

from .const import (
    IOT_NOTIFY_UUID,
    IOT_SERVICE_UUID,
    IOT_WRITE_UUID,
    NUS_NOTIFY_UUID,
    NUS_SERVICE_UUID,
    NUS_WRITE_UUID,
    POP_NOTIFY_UUID,
    POP_SERVICE_UUID,
    POP_WRITE_UUID,
    TRANSPORT_AUTO,
    TRANSPORT_IOT_GATT,
    TRANSPORT_NUS,
    TRANSPORT_POP,
)

_LOGGER = logging.getLogger(__name__)

_PROP_NOTIFY = frozenset({"notify", "indicate"})
_PROP_WRITE = frozenset({"write", "write-without-response"})


@dataclass(frozen=True, slots=True)
class ResolvedTransport:
    transport: str
    service_uuid: str
    write_uuid: str
    notify_uuid: str
    # IOT GATT (fd5abba0): Plus app sends via phone GATT-server notify, not client write.
    uses_gatt_server_write: bool = False


def _uuid_lower(value: str) -> str:
    return value.lower()


def _find_service(client: BleakClient, service_uuid: str):
    want = _uuid_lower(service_uuid)
    for service in client.services:
        if _uuid_lower(service.uuid) == want:
            return service
    return None


def _char_by_uuid(service, char_uuid: str):
    want = _uuid_lower(char_uuid)
    for char in service.characteristics:
        if _uuid_lower(char.uuid) == want:
            return char
    return None


def _char_props(char) -> set[str]:
    return set(char.properties)


def _pick_write_notify(service) -> tuple[str | None, str | None]:
    """Pick write + notify UUIDs on a service (may be the same characteristic)."""
    write_uuid: str | None = None
    notify_uuid: str | None = None
    combined: str | None = None

    for char in service.characteristics:
        props = _char_props(char)
        if props & _PROP_WRITE and props & _PROP_NOTIFY:
            combined = char.uuid
        if props & _PROP_WRITE and write_uuid is None:
            write_uuid = char.uuid
        if props & _PROP_NOTIFY and notify_uuid is None:
            notify_uuid = char.uuid

    if combined:
        return combined, combined
    if write_uuid and notify_uuid:
        return write_uuid, notify_uuid
    if write_uuid and notify_uuid is None:
        char = _char_by_uuid(service, write_uuid)
        if char and _char_props(char) & _PROP_NOTIFY:
            return write_uuid, write_uuid
    # Notify-only (IoT230 / E35i: fd5abba1 is notify on the robot side).
    if notify_uuid and write_uuid is None:
        return notify_uuid, notify_uuid
    return write_uuid, notify_uuid


def _try_fixed_profile(
    client: BleakClient,
    *,
    transport: str,
    service_uuid: str,
    write_uuid: str,
    notify_uuid: str,
) -> ResolvedTransport | None:
    service = _find_service(client, service_uuid)
    if service is None:
        return None

    write_char = _char_by_uuid(service, write_uuid)
    notify_char = _char_by_uuid(service, notify_uuid)
    if write_char is None or notify_char is None:
        inferred_write, inferred_notify = _pick_write_notify(service)
        if inferred_write is None and inferred_notify is not None:
            if transport == TRANSPORT_IOT_GATT:
                inferred_write = inferred_notify
        if inferred_write is None or inferred_notify is None:
            return None
        write_uuid = inferred_write
        notify_uuid = inferred_notify
    else:
        n_props = _char_props(notify_char)
        if not (n_props & _PROP_NOTIFY):
            return None
        if transport == TRANSPORT_IOT_GATT:
            # Plus APK: robot fd5abba1 is notify-only; commands go via phone GATT server.
            write_uuid = notify_char.uuid
            notify_uuid = notify_char.uuid
        else:
            w_props = _char_props(write_char)
            if not (w_props & _PROP_WRITE):
                return None

    return ResolvedTransport(
        transport,
        service_uuid,
        write_uuid,
        notify_uuid,
        uses_gatt_server_write=(transport == TRANSPORT_IOT_GATT),
    )


def _scan_generic_transports(client: BleakClient) -> list[ResolvedTransport]:
    """Last resort: any service with separate or combined write + notify."""
    found: list[ResolvedTransport] = []
    for service in client.services:
        write_uuid, notify_uuid = _pick_write_notify(service)
        if write_uuid is None or notify_uuid is None:
            continue
        svc = _uuid_lower(service.uuid)
        if svc in {
            _uuid_lower(IOT_SERVICE_UUID),
            _uuid_lower(NUS_SERVICE_UUID),
            _uuid_lower(POP_SERVICE_UUID),
        }:
            continue
        found.append(
            ResolvedTransport(
                TRANSPORT_AUTO,
                service.uuid,
                write_uuid,
                notify_uuid,
            )
        )
    return found


def _transport_candidates(preferred: str) -> list[tuple[str, str, str, str]]:
    profiles = [
        (TRANSPORT_IOT_GATT, IOT_SERVICE_UUID, IOT_WRITE_UUID, IOT_NOTIFY_UUID),
        (TRANSPORT_NUS, NUS_SERVICE_UUID, NUS_WRITE_UUID, NUS_NOTIFY_UUID),
        (TRANSPORT_POP, POP_SERVICE_UUID, POP_WRITE_UUID, POP_NOTIFY_UUID),
    ]
    if preferred == TRANSPORT_AUTO:
        return profiles
    if preferred in {p[0] for p in profiles}:
        return [row for row in profiles if row[0] == preferred]
    return profiles


def discover_transport(
    client: BleakClient, preferred: str
) -> ResolvedTransport | None:
    """Resolve service/write/notify UUIDs present on this robot."""
    for transport, service_uuid, write_uuid, notify_uuid in _transport_candidates(
        preferred
    ):
        resolved = _try_fixed_profile(
            client,
            transport=transport,
            service_uuid=service_uuid,
            write_uuid=write_uuid,
            notify_uuid=notify_uuid,
        )
        if resolved is not None:
            _LOGGER.info(
                "Dolphin Plus: BLE transport=%s (configured=%s) "
                "service=%s write=%s notify=%s gatt_server_write=%s",
                resolved.transport,
                preferred,
                resolved.service_uuid,
                resolved.write_uuid,
                resolved.notify_uuid,
                resolved.uses_gatt_server_write,
            )
            return resolved

    if preferred == TRANSPORT_AUTO:
        for resolved in _scan_generic_transports(client):
            _LOGGER.info(
                "Dolphin Plus: generic BLE transport service=%s write=%s notify=%s",
                resolved.service_uuid,
                resolved.write_uuid,
                resolved.notify_uuid,
            )
            return resolved

    log_gatt_services(client, level=logging.WARNING)
    _LOGGER.warning(
        "Dolphin Plus: no supported BLE transport found (preferred=%s)",
        preferred,
    )
    return None


def log_gatt_services(
    client: BleakClient, *, level: int = logging.DEBUG
) -> None:
    """Log discovered GATT tree (WARNING when setup fails)."""
    for service in client.services:
        chars = []
        for char in service.characteristics:
            chars.append(f"{char.uuid} [{','.join(char.properties)}]")
        _LOGGER.log(
            level,
            "Dolphin Plus GATT service %s → %s",
            service.uuid,
            "; ".join(chars) if chars else "(no characteristics)",
        )
