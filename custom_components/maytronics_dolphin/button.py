"""One-shot BLE actions (BTCommand on FFF8)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .connection import DolphinBleConnection
from .const import (
    COMMAND_CHAR_UUID,
    CONF_ADDRESS,
    CONF_NAME,
    DATA_BLE_SESSION,
    DATA_CARD_SUB,
    DATA_JOY,
    DOMAIN,
)
from .protocol import (
    BTCommandType,
    build_bt_command_19,
    build_joystick_packet,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register buttons."""
    entities: list[ButtonEntity] = [
        DolphinShortCommandButton(
            entry,
            "quit_rc_mode",
            "Quit RC mode",
            BTCommandType.QUITE_RC_MODE,
        ),
        DolphinShortCommandButton(
            entry,
            "reset_faults",
            "Reset faults",
            BTCommandType.RESET_FAULTS,
        ),
        DolphinShortCommandButton(
            entry,
            "home",
            "Home",
            BTCommandType.HOME,
        ),
        DolphinShortCommandButton(
            entry,
            "reset_dolphin",
            "Reset dolphin",
            BTCommandType.RESET_DOLPHIN,
        ),
        DolphinShortCommandButton(
            entry,
            "reset_filter_indication",
            "Reset filter indication",
            BTCommandType.RESET_FILTER_INDICATION,
        ),
        DolphinShortCommandButton(
            entry,
            "ping",
            "Ping",
            BTCommandType.PING,
        ),
        DolphinShortCommandButton(
            entry,
            "wall_sensor_poll",
            "Wall sensor poll",
            BTCommandType.WALL_SENSOR,
        ),
        DolphinLedTestButton(entry),
        DolphinJoystickSendButton(entry),
        DolphinCardTestRunButton(entry),
    ]
    async_add_entities(entities, update_before_add=False)


class _DolphinButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, key: str, title: str) -> None:
        super().__init__()
        self._entry = entry
        self._address = entry.data[CONF_ADDRESS]
        name = entry.data.get(CONF_NAME) or "Dolphin"
        self._attr_name = title
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Maytronics",
            model="Dolphin (BLE)",
            connections={(dr.CONNECTION_BLUETOOTH, dr.format_mac(self._address))},
        )

    async def _send(
        self,
        payload: bytes,
        *,
        pre: float = 0.3,
        post: float = 0.3,
    ) -> None:
        session: DolphinBleConnection = self.hass.data[DOMAIN][self._entry.entry_id][
            DATA_BLE_SESSION
        ]
        await session.async_send_gatt_packet(
            payload,
            COMMAND_CHAR_UUID,
            pre_write_delay=pre,
            post_write_delay=post,
        )


class DolphinShortCommandButton(_DolphinButton):
    """19-byte ``BTCommand.getBytes()`` (``BLEManager.writePacket`` style)."""

    def __init__(
        self, entry: ConfigEntry, key: str, title: str, cmd: BTCommandType
    ) -> None:
        super().__init__(entry, key, title)
        self._cmd = cmd

    async def async_press(self) -> None:
        await self._send(build_bt_command_19(self._cmd))


class DolphinLedTestButton(_DolphinButton):
    """Single-byte LED payload test (value=1)."""

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "led_test", "LED test (0x01)")

    async def async_press(self) -> None:
        await self._send(build_bt_command_19(BTCommandType.LEDS, led_value=1))


class DolphinJoystickSendButton(_DolphinButton):
    """Send joystick vector from number entities."""

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "joystick_send", "Send joystick")

    async def async_press(self) -> None:
        joy = self.hass.data[DOMAIN][self._entry.entry_id][DATA_JOY]
        payload = build_joystick_packet(joy["x"], joy["y"])
        await self._send(payload, pre=0.15, post=0.05)


class DolphinCardTestRunButton(_DolphinButton):
    """Run selected card self-test."""

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry, "card_test_run", "Run card test")

    async def async_press(self) -> None:
        sub = int(self.hass.data[DOMAIN][self._entry.entry_id][DATA_CARD_SUB])
        await self._send(
            build_bt_command_19(BTCommandType.CARD_TEST, card_subcommand=sub)
        )
