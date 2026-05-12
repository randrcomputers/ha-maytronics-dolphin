"""BT wire format: 3-byte short frames (CRC over SOP+cmd) and 19-byte BTCommand frames.

MyDolphin ``BLEManager.writePacket`` always sends ``BTCommand.getBytes()`` (19 bytes)
to ``BTCommand.UUID`` for ``turnOnRobot`` / ``turnOffRobot`` and simple commands
(``Quite_RC_mode``, ``Home``, ``Ping``, etc.). The 3-byte ``build_short_frame`` helpers
below are optional / HCI-sniff style only — they are **not** what the APK uses on FFF8.
"""

from __future__ import annotations

from enum import IntEnum

import struct

from .const import CMD_SHUTDOWN, CMD_STARTUP, POLYNOMIAL, SOP


def crc_run(data: bytes, length: int) -> int:
    """Same as MyDolphin `DolphinData.crcCalculation` for `length` leading bytes."""
    b = 0
    for idx in range(length):
        b = (b ^ (data[idx] & 0xFF)) & 0xFF
        for _ in range(8):
            if b & 0x80:
                b = ((b << 1) ^ POLYNOMIAL) & 0xFF
            else:
                b = (b << 1) & 0xFF
    return b & 0xFF


def build_short_frame(cmd: int) -> bytes:
    """3-byte ``[SOP, cmd, crc]`` — periodic / non-APK path; see module docstring."""
    buf = bytearray([SOP & 0xFF, cmd & 0xFF, 0])
    buf[2] = crc_run(bytes(buf[:2]), 2)
    return bytes(buf)


def finalize_19(buf: bytearray) -> bytes:
    """CRC over bytes 0..17 into byte 18 (`DolphinData.updateCRC`)."""
    if len(buf) != 19:
        raise ValueError("BTCommand frame must be length 19")
    buf[18] = crc_run(bytes(buf[:18]), 18)
    return bytes(buf)


class BTCommandType(IntEnum):
    """`com.maytronics.mydolphin.model.data.BTCommand.CommandType` (JADX / classes2.dex).

    UUID for this command set: ``0000fff8-0000-1000-8000-00805f9b34fb`` (`BTCommand.UUID`).

    The APK enum ends at ``Leds`` (iText ``BidiOrder.S`` == 16). There is **no**
    separate ``CommandType`` for “start normal clean” / “run cycle” — that flow
    uses these opcodes (e.g. ``Startup_dolphin``, ``Autoclean_Enable``) and/or
    other ``DolphinData`` writes (e.g. config on ``fff9``/``fffa``), not an extra
    FFF8 opcode.

    Ordinal layout matches ``BTCommand.getBytes()`` switch: only ``Leds``,
    ``Joystick_cmd``, ``Autoclean_Enable``, and ``Card_Test`` set payload bytes;
    all others leave ``bArr[2..17]`` zero after ``Arrays.fill``.
    """

    JOYSTICK = 3  # Joystick_cmd
    QUITE_RC_MODE = 4
    RESET_FAULTS = 5
    SHUTDOWN = 6
    STARTUP = 7
    HOME = 8
    RESET_DOLPHIN = 9
    RESET_FILTER_INDICATION = 10
    AUTOCLEAN_ENABLE = 11  # BidiOrder.AN
    WALL_SENSOR = 13  # BidiOrder.NSM
    CARD_TEST = 14  # BidiOrder.BN
    PING = 15  # BidiOrder.B
    LEDS = 16  # BidiOrder.S


def build_bt_command_19(
    cmd: BTCommandType,
    *,
    autoclean_on: bool | None = None,
    led_value: int | None = None,
    speed_a: int | None = None,
    speed_b: int | None = None,
    card_subcommand: int | None = None,
) -> bytes:
    """Mirror `BTCommand.getBytes()` layout (19 bytes, CRC at index 18)."""
    b = bytearray(19)
    b[0] = SOP & 0xFF
    b[1] = int(cmd) & 0xFF

    if cmd == BTCommandType.LEDS:
        if led_value is None:
            raise ValueError("led_value required for LEDS")
        b[2] = int(led_value) & 0xFF
    elif cmd == BTCommandType.JOYSTICK:
        if speed_a is None or speed_b is None:
            raise ValueError("speed_a and speed_b required for JOYSTICK")
        b[2] = int(speed_a) & 0xFF
        b[3] = int(speed_b) & 0xFF
    elif cmd == BTCommandType.AUTOCLEAN_ENABLE:
        if autoclean_on is None:
            raise ValueError("autoclean_on required for AUTOCLEAN_ENABLE")
        b[2] = 1 if autoclean_on else 0
    elif cmd == BTCommandType.CARD_TEST:
        if card_subcommand is None:
            raise ValueError("card_subcommand required for CARD_TEST (1..7)")
        sc = int(card_subcommand)
        if not 1 <= sc <= 7:
            raise ValueError("card_subcommand must be 1..7")
        b[2] = sc & 0xFF
    # else: payload bytes stay 0

    return finalize_19(b)


def payload_startup_short() -> bytes:
    """3-byte startup (not ``BLEManager.turnOnRobot`` — use ``build_bt_command_19(STARTUP)``)."""
    return build_short_frame(CMD_STARTUP)


def payload_shutdown_short() -> bytes:
    """3-byte shutdown (not ``BLEManager.turnOffRobot`` — use ``build_bt_command_19(SHUTDOWN)``)."""
    return build_short_frame(CMD_SHUTDOWN)


def build_short_cmd(cmd: BTCommandType) -> bytes:
    """3-byte frame for a ``CommandType`` code — not APK ``BTCommand.getBytes()``."""
    return build_short_frame(int(cmd))


def encode_joystick_axis(i: int) -> int:
    """Match `BLEManager.sendJoystickCommand` + `BTCommand.toBytes` low byte."""
    v = int(i)
    if v < 0:
        v = abs(v) | 128
    return struct.pack(">i", v)[3] & 0xFF


def build_joystick_packet(axis_x: int, axis_y: int) -> bytes:
    """19-byte joystick command."""
    return build_bt_command_19(
        BTCommandType.JOYSTICK,
        speed_a=encode_joystick_axis(axis_x),
        speed_b=encode_joystick_axis(axis_y),
    )
