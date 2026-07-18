"""Local BlueZ GATT server for IoT Plus send path (mirrors Plus app p/b/i + IotBleService)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .const import IOT_NOTIFY_UUID, IOT_SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"
GATT_MANAGER = "org.bluez.GattManager1"
GATT_CHRC = "org.bluez.GattCharacteristic1"
GATT_DESC = "org.bluez.GattDescriptor1"
GATT_SERVICE = "org.bluez.GattService1"
DBUS_OM = "org.freedesktop.DBus.ObjectManager"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"


class IotGattServer:
    """Register fd5abba0/fd5abba1 on BlueZ and notify subscribed centrals."""

    def __init__(self, suffix: str) -> None:
        safe = "".join(c if c.isalnum() else "_" for c in suffix)[-24:]
        self._root = f"/org/maytronics/dolphin_plus/{safe}"
        self._service_path = f"{self._root}/service0"
        self._char_path = f"{self._service_path}/char0"
        self._desc_path = f"{self._char_path}/desc0"
        self._app_path = f"{self._root}/app"
        self._bus: Any = None
        self._char: Any = None
        self._registered = False

    @property
    def notifying(self) -> bool:
        return bool(self._char and self._char._notifying)

    async def register(self) -> None:
        if self._registered:
            return
        try:
            from dbus_fast import Variant  # noqa: PLC0415
            from dbus_fast.aio import MessageBus  # noqa: PLC0415
            from dbus_fast.constants import BusType, PropertyAccess  # noqa: PLC0415
            from dbus_fast.service import ServiceInterface, dbus_property, method  # noqa: PLC0415
        except ImportError as err:
            raise RuntimeError("dbus_fast is required for IoT GATT server mode") from err

        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        char_holder: dict[str, Any] = {}

        class _Desc(ServiceInterface):
            def __init__(self, char_path: str) -> None:
                super().__init__(GATT_DESC)
                self._char_path = char_path

            @dbus_property(access=PropertyAccess.READ)
            def UUID(self) -> "s":  # type: ignore[valid-type]
                return CCCD_UUID

            @dbus_property(access=PropertyAccess.READ)
            def Characteristic(self) -> "o":  # type: ignore[valid-type]
                return self._char_path

            @dbus_property(access=PropertyAccess.READ)
            def Flags(self) -> "as":  # type: ignore[valid-type]
                return ["read", "write"]

            @method()
            def ReadValue(self, options: "a{sv}") -> "ay":  # type: ignore[valid-type]  # noqa: ARG002
                return bytes([0x00, 0x00])

            @method()
            def WriteValue(self, value: "ay", options: "a{sv}") -> "":  # type: ignore[valid-type]  # noqa: ARG002
                if value and value[0] & 0x01:
                    char_holder["iface"]._notifying = True
                    _LOGGER.info(
                        "Dolphin Plus: robot subscribed to local IoT GATT server"
                    )
                else:
                    char_holder["iface"]._notifying = False

        class _Char(ServiceInterface):
            def __init__(self, service_path: str, desc_path: str) -> None:
                super().__init__(GATT_CHRC)
                self._service_path = service_path
                self._desc_path = desc_path
                self._notifying = False
                self._value = bytearray()

            @dbus_property(access=PropertyAccess.READ)
            def UUID(self) -> "s":  # type: ignore[valid-type]
                return IOT_NOTIFY_UUID

            @dbus_property(access=PropertyAccess.READ)
            def Service(self) -> "o":  # type: ignore[valid-type]
                return self._service_path

            @dbus_property(access=PropertyAccess.READ)
            def Flags(self) -> "as":  # type: ignore[valid-type]
                return ["notify"]

            @dbus_property(access=PropertyAccess.READ)
            def Descriptors(self) -> "ao":  # type: ignore[valid-type]
                return [self._desc_path]

            @dbus_property(access=PropertyAccess.READ)
            def Value(self) -> "ay":  # type: ignore[valid-type]
                return bytes(self._value)

            @method()
            def StartNotify(self) -> "":
                self._notifying = True
                _LOGGER.info("Dolphin Plus: StartNotify on local IoT GATT char")

            @method()
            def StopNotify(self) -> "":
                self._notifying = False

        class _Service(ServiceInterface):
            def __init__(self, service_path: str, char_path: str) -> None:
                super().__init__(GATT_SERVICE)
                self._service_path = service_path
                self._char_path = char_path

            @dbus_property(access=PropertyAccess.READ)
            def UUID(self) -> "s":  # type: ignore[valid-type]
                return IOT_SERVICE_UUID

            @dbus_property(access=PropertyAccess.READ)
            def Primary(self) -> "b":  # type: ignore[valid-type]
                return True

            @dbus_property(access=PropertyAccess.READ)
            def Characteristics(self) -> "ao":  # type: ignore[valid-type]
                return [self._char_path]

        class _App(ServiceInterface):
            def __init__(
                self,
                service_path: str,
                char_path: str,
                desc_path: str,
            ) -> None:
                super().__init__(DBUS_OM)
                self._service_path = service_path
                self._char_path = char_path
                self._desc_path = desc_path

            @method()
            def GetManagedObjects(self) -> "a{oa{sa{sv}}}":  # type: ignore[valid-type]
                return {
                    self._service_path: {
                        GATT_SERVICE: {
                            "UUID": Variant("s", IOT_SERVICE_UUID),
                            "Primary": Variant("b", True),
                            "Characteristics": Variant("ao", [self._char_path]),
                        }
                    },
                    self._char_path: {
                        GATT_CHRC: {
                            "UUID": Variant("s", IOT_NOTIFY_UUID),
                            "Service": Variant("o", self._service_path),
                            "Flags": Variant("as", ["notify"]),
                            "Descriptors": Variant("ao", [self._desc_path]),
                        }
                    },
                    self._desc_path: {
                        GATT_DESC: {
                            "UUID": Variant("s", CCCD_UUID),
                            "Characteristic": Variant("o", self._char_path),
                            "Flags": Variant("as", ["read", "write"]),
                        }
                    },
                }

        desc = _Desc(self._char_path)
        char = _Char(self._service_path, self._desc_path)
        char_holder["iface"] = char
        service = _Service(self._service_path, self._char_path)
        app = _App(self._service_path, self._char_path, self._desc_path)

        for path, iface in (
            (self._app_path, app),
            (self._service_path, service),
            (self._char_path, char),
            (self._desc_path, desc),
        ):
            bus.export(path, iface)

        adapter = await self._find_adapter(bus)
        mgr = bus.get_proxy_object(BLUEZ, adapter, await bus.introspect(BLUEZ, adapter))
        gatt_mgr = mgr.get_interface(GATT_MANAGER)
        await gatt_mgr.call_register_application(self._app_path, {})

        self._bus = bus
        self._char = char
        self._registered = True
        _LOGGER.info(
            "Dolphin Plus: registered local IoT GATT server on %s", adapter
        )

    async def _find_adapter(self, bus: Any) -> str:
        om = bus.get_proxy_object(
            BLUEZ, "/", await bus.introspect(BLUEZ, "/")
        ).get_interface(DBUS_OM)
        objects = await om.call_get_managed_objects()
        for path, ifaces in objects.items():
            if GATT_MANAGER in ifaces and str(path).startswith("/org/bluez/hci"):
                return str(path)
        raise RuntimeError("No BlueZ adapter with GattManager1 found")

    async def notify(self, payload: bytes, *, wait_subscriber_sec: float = 5.0) -> bool:
        if not self._registered or self._char is None:
            return False
        deadline = asyncio.get_running_loop().time() + wait_subscriber_sec
        while asyncio.get_running_loop().time() < deadline:
            if self._char._notifying:
                break
            await asyncio.sleep(0.1)
        if not self._char._notifying:
            _LOGGER.warning(
                "Dolphin Plus: robot has not subscribed to local IoT GATT server yet"
            )
            return False
        self._char._value = bytearray(payload)
        self._char.emit_properties_changed({"Value": payload}, [])
        _LOGGER.info(
            "Dolphin Plus: IoT GATT server notify sent (%d bytes): %s",
            len(payload),
            payload.hex(),
        )
        return True

    async def unregister(self) -> None:
        if not self._registered or self._bus is None:
            return
        try:
            adapter = await self._find_adapter(self._bus)
            mgr = self._bus.get_proxy_object(
                BLUEZ, adapter, await self._bus.introspect(BLUEZ, adapter)
            ).get_interface(GATT_MANAGER)
            await mgr.call_unregister_application(self._app_path)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("IoT GATT server unregister: %s", err)
        self._registered = False
        self._bus = None
        self._char = None
