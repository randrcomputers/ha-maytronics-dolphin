"""ConfigParamsRead / Write wire helpers (MyDolphin ``DolphinData`` on ``fff0`` service).

JADX class UUIDs (swap‑fixed in ``const.py``): ``ConfigParamsRead`` → ``fffa``,
``ConfigParamsWrite`` → ``fff9``. Response ``getAckDataLength()`` for read is 47 bytes;
request buffer matches that layout with ``DolphinData``‑style CRC in the last byte.
"""

from __future__ import annotations

from enum import IntEnum

from .const import SOP
from .protocol import crc_run

# ``com.maytronics.mydolphin.model.data.ConfigParamsRead.CommandType`` — PS_State (BidiOrder.NSM).
CONFIG_PARAMS_CMD_PS_STATE = 13


class PSState(IntEnum):
    """``ConfigParamsRead.getAck`` PS_State branch (byte after SOP, cmd, err)."""

    OFF = 0
    ON = 1
    HOLD = 2
    PROGRAMMING = 3
    BIST = 4


def build_config_params_read_request(command_code: int = CONFIG_PARAMS_CMD_PS_STATE) -> bytes:
    """47-byte read request: ``[SOP, cmd, 0…0, CRC]`` (CRC over first 46 bytes)."""
    buf = bytearray(47)
    buf[0] = SOP & 0xFF
    buf[1] = int(command_code) & 0xFF
    buf[46] = crc_run(bytes(buf[:46]), 46)
    return bytes(buf)


def _crc_ok_47(frame: bytes, start: int) -> bool:
    if start + 47 > len(frame):
        return False
    chunk = frame[start : start + 47]
    return chunk[46] == crc_run(chunk[:46], 46)


def parse_config_params_ps_state(data: bytes) -> PSState | None:
    """Minimal port of ``ConfigParamsRead.getAck`` for ``PS_State`` (cmd 13)."""
    if not data or len(data) < 4:
        return None
    i = 0
    while i < len(data):
        if data[i] != SOP:
            i += 1
            continue
        if i + 3 >= len(data):
            return None
        if data[i + 1] != CONFIG_PARAMS_CMD_PS_STATE:
            i += 1
            continue
        if data[i + 2] != 0:
            return None
        ps_byte = data[i + 3]
        if i + 47 <= len(data) and not _crc_ok_47(data, i):
            i += 1
            continue
        try:
            return PSState(ps_byte)
        except ValueError:
            return None
    return None


def ps_state_implies_power_on(state: PSState | None) -> bool | None:
    """HA Power switch: off only when robot reports OFF."""
    if state is None:
        return None
    if state == PSState.OFF:
        return False
    return True
