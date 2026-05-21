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
                "ConfigParamsRead cmd %s CRC mismatch (using byte %s); frame=%s",
                command_code,
                value,
                data[i : i + 47].hex(),
            )
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


def ps_state_implies_power_on(state: PSState | None) -> bool | None:
    """HA Power switch: off only when robot reports OFF."""
    if state is None:
        return None
    if state == PSState.OFF:
        return False
    return True


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
