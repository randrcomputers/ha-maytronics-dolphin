"""Plus app IoT BLE frame builder (from ``ble_iot_protocol.json`` + APK 3.4).

IoT checksum: 16-bit unsigned sum of all preceding bytes, big-endian (``Lq/f.a``).

Outbound IoT GATT notify payloads are ASCII hex envelopes (not raw binary), e.g.
``03:ab03fff806000002ab``. Inbound robot notifications use the same ``:`` envelope
with a variable prefix; long frames are split across notify chunks.
"""

from __future__ import annotations

import json
import logging
import re
from enum import IntEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SOP_IOT = 0xAB
SRC_IOT = 0x03
IOT_HEADER_LEN = 7  # sop + src + dest(2) + opcode + data_len(2)
IOT_CHECKSUM_LEN = 2

# Host→robot notify envelope used by Plus IoT PSUs (ESPHome + APK capture).
IOT_NOTIFY_PREFIX = "03:"

CMD_START_UP = "start_up_dolphin"
CMD_SHUTDOWN = "shutdown_dolphin"
CMD_SYSTEM_STATUS = "system_status"

_HEX_CHARS = re.compile(rb"^[0-9a-fA-F]+$")


class PowerState(IntEnum):
    """Inferred from ``system_status.sm_state`` (0 = off, non-zero = on)."""

    OFF = 0
    ON = 1
    UNKNOWN = -1


def _protocol_json_path(profile: str) -> Path:
    base = Path(__file__).resolve().parent / "protocols"
    name = {
        "iot": "ble_iot_protocol.json",
        "pop": "ble_pop_protocol.json",
        "buoy": "ble_buoy_protocol.json",
    }.get(profile, "ble_iot_protocol.json")
    return base / name


@lru_cache(maxsize=4)
def load_protocol_spec(profile: str) -> dict[str, Any]:
    path = _protocol_json_path(profile)
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


async def async_load_protocol_spec(
    hass: HomeAssistant, profile: str
) -> dict[str, Any]:
    """Load protocol JSON off the event loop (avoids blocking-call warnings)."""
    return await hass.async_add_executor_job(load_protocol_spec, profile)


def iot_checksum(data: bytes) -> bytes:
    total = sum(b & 0xFF for b in data) & 0xFFFF
    return bytes([(total >> 8) & 0xFF, total & 0xFF])


def _hex_to_bytes(value: str) -> bytes:
    cleaned = value.strip().replace(" ", "")
    if len(cleaned) % 2:
        cleaned = "0" + cleaned
    return bytes.fromhex(cleaned)


def build_iot_command(
    spec: dict[str, Any],
    command_name: str,
    payload: bytes = b"",
) -> bytes:
    """Build a single IoT-protocol request frame."""
    commands = spec.get("commands") or {}
    if command_name not in commands:
        raise ValueError(f"Unknown command: {command_name}")
    cmd = commands[command_name]
    dest = _hex_to_bytes(str(cmd["destination"]))
    opcode = _hex_to_bytes(str(cmd["opcode"]))
    if len(dest) != 2:
        raise ValueError(f"destination must be 2 bytes: {cmd['destination']}")
    if len(opcode) != 1:
        raise ValueError(f"opcode must be 1 byte: {cmd['opcode']}")

    data_len = len(payload)
    header = bytes(
        [
            SOP_IOT,
            SRC_IOT,
            dest[0],
            dest[1],
            opcode[0],
            (data_len >> 8) & 0xFF,
            data_len & 0xFF,
        ]
    )
    body = header + payload
    return body + iot_checksum(body)


def build_startup(spec: dict[str, Any]) -> bytes:
    return build_iot_command(spec, CMD_START_UP)


def build_shutdown(spec: dict[str, Any]) -> bytes:
    return build_iot_command(spec, CMD_SHUTDOWN)


def build_system_status_request(spec: dict[str, Any]) -> bytes:
    return build_iot_command(spec, CMD_SYSTEM_STATUS)


def encode_iot_notify_text(frame: bytes) -> bytes:
    """Wrap a binary IoT frame for GATT-server notify (ASCII ``03:<hex>``)."""
    return (IOT_NOTIFY_PREFIX + frame.hex()).encode("ascii")


def looks_like_iot_ascii_chunk(data: bytes) -> bool:
    """True if a notify chunk looks like Plus ASCII envelope text."""
    if not data:
        return False
    if b":" in data:
        return True
    sample = data[:min(len(data), 32)]
    return bool(_HEX_CHARS.match(sample))


def _verify_iot_checksum(frame: bytes) -> bool:
    if len(frame) < IOT_HEADER_LEN + IOT_CHECKSUM_LEN:
        return False
    body, cs = frame[:-IOT_CHECKSUM_LEN], frame[-IOT_CHECKSUM_LEN:]
    return iot_checksum(body) == cs


def iter_iot_frames(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Split accumulated *binary* notify data into complete IoT frames."""
    frames: list[bytes] = []
    i = 0
    while i < len(buffer):
        if buffer[i] != SOP_IOT:
            i += 1
            continue
        if i + IOT_HEADER_LEN > len(buffer):
            break
        data_len = (buffer[i + 5] << 8) | buffer[i + 6]
        total = IOT_HEADER_LEN + data_len + IOT_CHECKSUM_LEN
        if i + total > len(buffer):
            break
        frame = buffer[i : i + total]
        if _verify_iot_checksum(frame):
            frames.append(frame)
        else:
            _LOGGER.debug("Plus BLE: dropping frame with bad checksum: %s", frame.hex())
        i += total
    return frames, buffer[i:]


class IotAsciiRxBuffer:
    """Reassemble IoT ASCII notify chunks (``[prefix]:<hex>``) into binary frames."""

    def __init__(self) -> None:
        self._text = ""

    def feed(self, chunk: bytes) -> list[bytes]:
        try:
            text = chunk.decode("ascii", errors="ignore")
        except Exception:  # noqa: BLE001
            return []
        if not text:
            return []

        if not self._text:
            colon = text.find(":")
            if colon < 0:
                return []
            self._text = text[colon:]
        else:
            self._text += text

        return self._drain()

    @property
    def pending(self) -> bool:
        return bool(self._text)

    def _drain(self) -> list[bytes]:
        frames: list[bytes] = []
        while self._text:
            colon = self._text.find(":")
            if colon < 0:
                self._text = ""
                break
            if colon > 0:
                self._text = self._text[colon:]

            hex_part = self._text[1:]
            if len(hex_part) < IOT_HEADER_LEN * 2:
                break
            try:
                header = bytes.fromhex(hex_part[: IOT_HEADER_LEN * 2])
            except ValueError:
                _LOGGER.debug("Plus BLE: bad ASCII header; clearing rx buffer")
                self._text = ""
                break
            if len(header) < IOT_HEADER_LEN or header[0] != SOP_IOT:
                self._text = ""
                break

            data_len = (header[5] << 8) | header[6]
            frame_len = IOT_HEADER_LEN + data_len + IOT_CHECKSUM_LEN
            need_hex = frame_len * 2
            if len(hex_part) < need_hex:
                break
            try:
                frame = bytes.fromhex(hex_part[:need_hex])
            except ValueError:
                _LOGGER.debug("Plus BLE: bad ASCII frame hex; clearing rx buffer")
                self._text = ""
                break
            self._text = hex_part[need_hex:]
            if _verify_iot_checksum(frame):
                frames.append(frame)
            else:
                _LOGGER.debug(
                    "Plus BLE: dropping ASCII frame with bad checksum: %s",
                    frame.hex(),
                )
        return frames


def parse_iot_frame_payload(frame: bytes) -> tuple[int, int, bytes]:
    """Return (opcode, data_len, payload including leading ACK when present)."""
    if len(frame) < IOT_HEADER_LEN + IOT_CHECKSUM_LEN:
        raise ValueError("frame too short")
    opcode = frame[4]
    data_len = (frame[5] << 8) | frame[6]
    payload = frame[IOT_HEADER_LEN : IOT_HEADER_LEN + data_len]
    return opcode, data_len, payload


def parse_system_status(payload: bytes) -> dict[str, int | None]:
    """Map ``system_status`` response bytes after removing the leading ACK."""
    # Wire layout: ACK + mu_state + sm_state + filter + cleaning_mode + ...
    data = payload[1:] if payload else b""
    if len(data) < 2:
        return {"mu_state": None, "sm_state": None, "cleaning_mode": None}
    return {
        "mu_state": data[0],
        "sm_state": data[1],
        "cleaning_mode": data[3] if len(data) > 3 else None,
    }


def sm_state_implies_power_on(sm_state: int | None) -> bool | None:
    if sm_state is None:
        return None
    return sm_state != 0


def sm_state_to_power_state(sm_state: int | None) -> PowerState:
    inferred = sm_state_implies_power_on(sm_state)
    if inferred is None:
        return PowerState.UNKNOWN
    return PowerState.ON if inferred else PowerState.OFF
