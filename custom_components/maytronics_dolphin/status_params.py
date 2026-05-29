"""GetStatusRead / InternalParamsRead helpers (MyDolphin 2.3.19 APK)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from .config_params import CleanMode, PSState, build_short_frame
from .const import SOP

_LOGGER = logging.getLogger(__name__)

# ``GetStatusRead.getBytes()`` → ``[SOP, 0x01, crc]``; ``getAckDataLength`` = 12.
GET_STATUS_CMD = 0x01
GET_STATUS_ACK_LEN = 12

# ``InternalParamsRead.getBytes()`` → ``[SOP, 0x01, crc]``; ``getAckDataLength`` = 132.
INTERNAL_PARAMS_CMD = 0x01
INTERNAL_PARAMS_MIN_LEN = 122

# ``InternalParamsRead.getAck`` with PS on uses data base index **3** (error byte at index 2).
_INTERNAL_BASE_WHEN_PS_ON = 3
# APK marks ``floor_only`` when clean byte is 1 and climb-every byte is 234 (0xEA).
_FLOOR_ONLY_CLIMB_MARKER = 234

# Offsets from ``v7 + N`` in ``InternalParamsRead.getAck`` (PS on, base=3).
_OFF_CLEAN_MODE = 9
_OFF_CLIMB_EVERY = 31
_OFF_MOTOR_AUX = 21
_OFF_PHASE = 30
_OFF_ALT_CLEAN = 41
_OFF_DOLPHIN_ERROR = 118


class WorkingStatus(StrEnum):
    """``GetStatusRead$WorkingStatus``."""

    AT_WORK = "at_work"
    FINISHED = "finished"
    FAULT = "fault"
    UNKNOWN = "unknown"


class CleaningSurface(StrEnum):
    """Best-effort live surface (not all models expose a dedicated wall/floor byte)."""

    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    FLOOR = "floor"
    WALL = "wall"
    WATERLINE = "waterline"


@dataclass(frozen=True)
class InternalParamsSnapshot:
    """Subset of the 132-byte ``InternalParamsRead`` notify."""

    clean_mode_byte: int
    climb_every: int
    motor_aux: int
    phase_byte: int
    alt_clean_byte: int
    dolphin_error: int


def build_get_status_read_request() -> bytes:
    """3-byte read trigger for ``fffc`` (same layout as ``GetStatusRead.getBytes``)."""
    return build_short_frame(GET_STATUS_CMD)


def build_internal_params_read_request() -> bytes:
    """3-byte read trigger for ``fffd`` (``InternalParamsRead.getBytes``)."""
    return build_short_frame(INTERNAL_PARAMS_CMD)


def _internal_data_base(data: bytes) -> int | None:
    """Locate payload start: ``[SOP][cmd][err==0][payload…]`` or PS-on style at index 3."""
    if len(data) >= _INTERNAL_BASE_WHEN_PS_ON + 20:
        if data[2] == 0:
            return _INTERNAL_BASE_WHEN_PS_ON
    i = 0
    while i < len(data):
        if data[i] != SOP:
            i += 1
            continue
        if i + 2 >= len(data) or data[i + 2] != 0:
            i += 1
            continue
        return i + 3
    return None


def parse_internal_params_snapshot(data: bytes) -> InternalParamsSnapshot | None:
    """Parse internal params notify (132-byte APK ``getAck`` layout, PS-on offsets)."""
    base = _internal_data_base(data)
    if base is None or len(data) < base + _OFF_DOLPHIN_ERROR + 1:
        return None
    return InternalParamsSnapshot(
        clean_mode_byte=data[base + _OFF_CLEAN_MODE] & 0xFF,
        climb_every=data[base + _OFF_CLIMB_EVERY] & 0xFF,
        motor_aux=data[base + _OFF_MOTOR_AUX] & 0xFF,
        phase_byte=data[base + _OFF_PHASE] & 0xFF,
        alt_clean_byte=data[base + _OFF_ALT_CLEAN] & 0xFF,
        dolphin_error=data[base + _OFF_DOLPHIN_ERROR] & 0xFF,
    )


def is_floor_only_marker(snap: InternalParamsSnapshot | None) -> bool:
    """APK rewrites ``regular``+climb 234 to ``floor_only`` in ``InternalParamsRead.getAck``."""
    if snap is None:
        return False
    return (
        snap.clean_mode_byte == int(CleanMode.REGULAR)
        and snap.climb_every == _FLOOR_ONLY_CLIMB_MARKER
    )


def resolve_working_status(
    ps: PSState | None,
    gatt: WorkingStatus | None,
    internal: InternalParamsSnapshot | None,
) -> WorkingStatus | None:
    """Prefer ``GetStatusRead``; infer from PS + internal bytes when fffc ack is missing."""
    if ps is None or ps == PSState.OFF:
        return None
    if ps == PSState.HOLD:
        return WorkingStatus.FINISHED
    if gatt is not None and gatt != WorkingStatus.UNKNOWN:
        return gatt
    if internal is not None:
        if internal.dolphin_error != 0:
            return WorkingStatus.FAULT
        if internal.motor_aux > 0 or internal.phase_byte in (1, 0x01):
            return WorkingStatus.AT_WORK
        return WorkingStatus.FINISHED
    if gatt == WorkingStatus.FAULT:
        return WorkingStatus.FAULT
    return None


def _working_from_code(code: int) -> WorkingStatus | None:
    if code == 0:
        return WorkingStatus.AT_WORK
    if code == 1:
        return WorkingStatus.FINISHED
    if code == 2:
        return WorkingStatus.FAULT
    if code == 0xFF:
        return None
    return WorkingStatus.UNKNOWN


def parse_get_status_working(data: bytes) -> WorkingStatus | None:
    """``GetStatusRead.getAck``: working @+4 (APK); some models omit cmd byte in notify."""
    i = 0
    while i < len(data):
        if data[i] != SOP:
            i += 1
            continue
        if i + 5 >= len(data):
            return None
        if data[i + 2] != 0:
            i += 1
            continue
        for off in (4, 3):
            if i + off >= len(data):
                continue
            if off == 3 and data[i + 1] == GET_STATUS_CMD:
                continue
            parsed = _working_from_code(data[i + off] & 0xFF)
            if parsed in (
                WorkingStatus.AT_WORK,
                WorkingStatus.FINISHED,
                WorkingStatus.FAULT,
            ):
                return parsed
        i += 1
    return None


def infer_cleaning_surface(
    ps: PSState | None,
    clean_mode: CleanMode | None,
    internal: InternalParamsSnapshot | None,
    *,
    working: WorkingStatus | None = None,
) -> CleaningSurface:
    """Infer surface from program + internal bytes (live wall/floor is not a first-class APK field)."""
    if ps is None or ps == PSState.OFF:
        return CleaningSurface.UNAVAILABLE
    if working == WorkingStatus.FAULT:
        return CleaningSurface.UNKNOWN
    if is_floor_only_marker(internal):
        return CleaningSurface.FLOOR
    if clean_mode == CleanMode.WATERLINE:
        return CleaningSurface.WATERLINE
    if clean_mode in (CleanMode.REGULAR, CleanMode.FAST_MODE, CleanMode.DYNAMIC_FAST_CLEAN):
        return CleaningSurface.FLOOR
    if clean_mode == CleanMode.ULTRACLEAN:
        if internal is not None:
            # Experimental: phase byte at APK offset 30 — validate on your model via debug logs.
            if internal.phase_byte in (1, 0x01):
                return CleaningSurface.WALL
            if internal.phase_byte in (0, 2, 0x02):
                return CleaningSurface.FLOOR
        return CleaningSurface.UNKNOWN
    if clean_mode in (CleanMode.SWIMMER, CleanMode.LINE_TO, CleanMode.TIC_TAC):
        return CleaningSurface.UNKNOWN
    return CleaningSurface.UNKNOWN
