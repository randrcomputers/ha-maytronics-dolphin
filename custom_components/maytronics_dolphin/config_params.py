"""ConfigParamsRead / Write wire helpers (MyDolphin ``DolphinData`` on ``fff0`` service).

Characteristic UUIDs (swap‑fixed in ``const.py``): ``ConfigParamsRead`` → ``fffa``,
``ConfigParamsWrite`` → ``fff9``.

MyDolphin 2.3.19 (``classes2.dex``): ``ConfigParamsRead.getBytes()`` allocates **3**
bytes, fills zeros, sets ``buf[0]=SOP``, ``buf[1]=CommandType.CODE``, then
``DolphinData.updateCRC`` (CRC over ``length-1`` bytes → last byte). The read **ACK**
payload length from ``getAckDataLength()`` is **47** bytes — that is the notify
payload, not the outgoing write length.
"""

from __future__ import annotations

import logging
from enum import IntEnum

from .const import SOP
from .protocol import build_short_frame, crc_run

_LOGGER = logging.getLogger(__name__)

# ``ConfigParamsRead$CommandType`` wire ``CODE`` bytes (APK 2.3.19 ``classes2.dex``).
CONFIG_PARAMS_CMD_PS_STATE = 13
CONFIG_PARAMS_CMD_WORKING_CLEAN_MODE = 5
# APK ``Cycle_Time`` / write ``cycle_time`` (``BLEManager.setCicleTime``).
CONFIG_PARAMS_CMD_CYCLE_TIME = 1

# ``ConfigParamsWrite.getBytes()`` allocates 46 bytes (CRC in last).
CONFIG_PARAMS_WRITE_LEN = 46
CONFIG_PARAMS_WRITE_ARGS_LEN = 43

# ``setCicleTime`` divides minutes by 6 before packing the low byte.
CYCLE_TIME_UNIT_MINUTES = 6
CYCLE_TIME_MINUTES_1H = 60
CYCLE_TIME_MINUTES_2H = 120


class PSState(IntEnum):
    """``ConfigParamsRead.getAck`` PS_State branch (byte after SOP, cmd, err)."""

    OFF = 0
    ON = 1
    HOLD = 2
    PROGRAMMING = 3
    BIST = 4


class CleanMode(IntEnum):
    """``ConfigParamsRead$CleanMode`` wire ``CODE`` (``CleanMode.get(B)`` matches on CODE)."""

    REGULAR = 1
    ULTRACLEAN = 2
    SWIMMER = 3
    WATERLINE = 4
    FAST_MODE = 5
    LINE_TO = 6
    DYNAMIC_FAST_CLEAN = 7
    TIC_TAC = 0x98  # APK ``tic_tac`` uses signed byte **-104**


def build_config_params_read_request(command_code: int = CONFIG_PARAMS_CMD_PS_STATE) -> bytes:
    """Same on-air layout as APK ``ConfigParamsRead.getBytes()`` — ``[SOP, cmd, crc]``."""
    return build_short_frame(int(command_code) & 0xFF)


def _crc_ok_47(frame: bytes, start: int) -> bool:
    if start + 47 > len(frame):
        return False
    chunk = frame[start : start + 47]
    return chunk[46] == crc_run(chunk[:46], 46)


def _parse_config_params_ack_byte(data: bytes, command_code: int) -> int | None:
    """Port of ``ConfigParamsRead.getAck``: byte at offset 3 when ``[SOP,cmd,err==0]``."""
    if not data:
        return None
    i = 0
    while i < len(data):
        if data[i] != SOP:
            i += 1
            continue
        if i + 3 >= len(data):
            return None
        if data[i + 1] != (int(command_code) & 0xFF):
            i += 1
            continue
        if data[i + 2] != 0:
            return None
        value = data[i + 3]
        if value == 0xFF:
            return None
        if i + 47 <= len(data) and not _crc_ok_47(data, i):
            _LOGGER.debug(
                "ConfigParamsRead cmd %s CRC mismatch (rejecting); frame=%s",
                command_code,
                data[i : i + 47].hex(),
            )
            return None
        return value
    return None


def parse_config_params_ps_state(data: bytes) -> PSState | None:
    """Minimal port of ``ConfigParamsRead.getAck`` for ``PS_State`` (wire cmd **13**)."""
    ps_byte = _parse_config_params_ack_byte(data, CONFIG_PARAMS_CMD_PS_STATE)
    if ps_byte is None:
        return None
    try:
        return PSState(ps_byte)
    except ValueError:
        return None


def parse_config_params_clean_mode(data: bytes) -> CleanMode | None:
    """``ConfigParamsRead.getAck`` → ``CleanMode.get(B)`` for ``Working_Clean_Mode`` (cmd **5**)."""
    mode_byte = _parse_config_params_ack_byte(data, CONFIG_PARAMS_CMD_WORKING_CLEAN_MODE)
    if mode_byte is None:
        return None
    try:
        return CleanMode(mode_byte)
    except ValueError:
        return None


def parse_config_params_cycle_time_minutes(data: bytes) -> int | None:
    """``ConfigParamsRead`` ``Cycle_Time`` (cmd **1**) → minutes (APK stores units of 6 min)."""
    units = _parse_config_params_ack_byte(data, CONFIG_PARAMS_CMD_CYCLE_TIME)
    if units is None or units <= 0:
        return None
    return int(units) * CYCLE_TIME_UNIT_MINUTES


def build_config_params_write_cycle_time(minutes: int) -> bytes:
    """Mirror ``BLEManager.setCicleTime`` → ``ConfigParamsWrite(cycle_time)`` on ``fff9``.

    APK divides minutes by 6, packs the low byte of that unit into ``mArgs[0]``,
    writes ``0xFF`` terminator in ``mArgs[1]``, then CRC over the 46-byte frame.
    """
    minutes = int(minutes)
    if minutes not in (CYCLE_TIME_MINUTES_1H, CYCLE_TIME_MINUTES_2H):
        raise ValueError("cycle time must be 60 or 120 minutes")
    units = minutes // CYCLE_TIME_UNIT_MINUTES
    buf = bytearray(CONFIG_PARAMS_WRITE_LEN)
    buf[0] = SOP & 0xFF
    buf[1] = CONFIG_PARAMS_CMD_CYCLE_TIME & 0xFF
    # mArgs start at index 2 (43 bytes); pack low byte of units then 0xFF sentinel.
    buf[2] = units & 0xFF
    buf[3] = 0xFF
    buf[CONFIG_PARAMS_WRITE_LEN - 1] = crc_run(bytes(buf[: CONFIG_PARAMS_WRITE_LEN - 1]), CONFIG_PARAMS_WRITE_LEN - 1)
    return bytes(buf)


def cycle_time_label(minutes: int | None) -> str | None:
    """HA select option for known cycle lengths."""
    if minutes == CYCLE_TIME_MINUTES_1H:
        return "1 hour"
    if minutes == CYCLE_TIME_MINUTES_2H:
        return "2 hours"
    return None


def cycle_time_minutes_from_label(label: str) -> int:
    if label == "1 hour":
        return CYCLE_TIME_MINUTES_1H
    if label == "2 hours":
        return CYCLE_TIME_MINUTES_2H
    raise ValueError(f"unknown cycle time label: {label}")


def ps_state_implies_power_on(state: PSState | None) -> bool | None:
    """HA Power switch display: off only when robot reports OFF."""
    if state is None:
        return None
    if state == PSState.OFF:
        return False
    return True


def ps_state_matches_power_command(state: PSState | None, *, expect_on: bool) -> bool:
    """Confirm a STARTUP/SHUTDOWN command — stricter than switch display state."""
    if state is None:
        return False
    if expect_on:
        return state == PSState.ON
    return state == PSState.OFF


PS_STATE_LABEL: dict[PSState, str] = {
    PSState.OFF: "off",
    PSState.ON: "on",
    PSState.HOLD: "hold",
    PSState.PROGRAMMING: "programming",
    PSState.BIST: "self_test",
}


def ps_state_to_str(state: PSState | None) -> str:
    """Human-readable cleaner state for ``sensor`` entities."""
    if state is None:
        return "unknown"
    return PS_STATE_LABEL.get(state, f"unknown_code_{int(state)}")


def ps_state_cleaning_active(state: PSState | None) -> bool | None:
    """True when robot is not fully off (includes hold / programming / BIST)."""
    if state is None:
        return None
    return state != PSState.OFF


CLEAN_MODE_LABEL: dict[CleanMode, str] = {
    CleanMode.REGULAR: "regular",
    CleanMode.ULTRACLEAN: "ultraclean",
    CleanMode.SWIMMER: "swimmer",
    CleanMode.WATERLINE: "waterline",
    CleanMode.FAST_MODE: "fast_mode",
    CleanMode.LINE_TO: "line_to",
    CleanMode.DYNAMIC_FAST_CLEAN: "dynamic_fast_clean",
    CleanMode.TIC_TAC: "tic_tac",
}


def clean_mode_to_str(mode: CleanMode | None) -> str:
    """Human-readable clean program for sensor entities."""
    if mode is None:
        return "unknown"
    return CLEAN_MODE_LABEL.get(mode, f"unknown_code_{int(mode)}")
