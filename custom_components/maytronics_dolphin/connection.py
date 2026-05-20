"""BLE client for Maytronics Dolphin — short sessions (connect, work, disconnect).

Holding an idle GATT link wedges some robots (BT LED stays on, unit frozen until
power cycle). We release the link after every command and poll.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ble import _noop_notify, async_resolve_ble_device
from .config_params import (
    PSState,
    build_config_params_read_request,
    parse_config_params_ps_state,
)
from .const import (
    CONFIG_PARAMS_READ_UUID,
    CONFIG_PARAMS_WRITE_UUID,
    DATA_BLE_SESSION,
    DOMAIN,
    GET_STATUS_READ_UUID,
    INTERNAL_PARAMS_READ_UUID,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_DIAGNOSTIC_PROBE,
)
from .options import get_integration_options

_LOGGER = logging.getLogger(__name__)

_PS_READ_PER_STRATEGY_TIMEOUT = 3.5
_PS_FAIL_LOG_INTERVAL_SEC = 300.0
_PS_MAX_STRATEGIES = 2
_GATT_READ_PROBE_TIMEOUT = 4.0
_BLE_CONNECT_TIMEOUT = 35.0


class _PsFailLogThrottle:
    last_monotonic: float = 0.0


def _throttled_ps_fail_warning(message: str) -> None:
    now = time.monotonic()
    if now - _PsFailLogThrottle.last_monotonic >= _PS_FAIL_LOG_INTERVAL_SEC:
        _PsFailLogThrottle.last_monotonic = now
        _LOGGER.warning("%s", message)


class DolphinBleConnection:
    """Connect only for each operation, then disconnect so the robot can run."""

    def __init__(self, hass: HomeAssistant, address: str, entry_id: str) -> None:
        self.hass = hass
        self.address = address
        self._entry_id = entry_id
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._shutting_down = False

    def mark_shutting_down(self) -> None:
        self._shutting_down = True

    @property
    def is_connected(self) -> bool:
        c = self._client
        return c is not None and c.is_connected

    def _options(self) -> dict[str, int | bool]:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return {}
        return get_integration_options(entry)

    async def async_disconnect(self) -> None:
        self._shutting_down = True
        async with self._lock:
            await self._disconnect_locked()

    async def _disconnect_locked(self) -> None:
        if self._client is None:
            return
        try:
            if self._client.is_connected:
                await self._client.disconnect()
                _LOGGER.debug("Maytronics Dolphin: BLE released")
        except BleakError:
            _LOGGER.debug("disconnect raised BleakError (ignored)", exc_info=True)
        self._client = None

    async def _ensure_connected_locked(self) -> BleakClientWithServiceCache:
        if self._shutting_down:
            raise HomeAssistantError("Maytronics Dolphin BLE is shutting down")
        if self._client is not None and self._client.is_connected:
            return self._client

        await self._disconnect_locked()

        ble_device = await async_resolve_ble_device(self.hass, self.address)
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            name=ble_device.name or self.address,
            timeout=_BLE_CONNECT_TIMEOUT,
        )
        if not client.is_connected:
            raise HomeAssistantError("Failed to connect over BLE")
        self._client = client
        _LOGGER.debug(
            "Maytronics Dolphin: BLE connected (%s)",
            ble_device.address,
        )
        return self._client

    async def async_release_ble_link(self) -> None:
        """Drop GATT if held (frees robot when link was wedged)."""
        if self._shutting_down:
            return
        try:
            async with self._lock:
                await self._disconnect_locked()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("release BLE: %s", err)

    async def async_send_gatt_packet(
        self,
        payload: bytes,
        char_uuid: str,
        *,
        pre_write_delay: float = 0.3,
        post_write_delay: float = 0.3,
    ) -> None:
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
                await client.start_notify(char_uuid, _noop_notify)
                await asyncio.sleep(pre_write_delay)
                await client.write_gatt_char(char_uuid, payload, response=True)
                await asyncio.sleep(post_write_delay)
                try:
                    await client.stop_notify(char_uuid)
                except BleakError:
                    _LOGGER.debug("stop_notify failed (ignored)", exc_info=True)
            except BleakError as err:
                raise HomeAssistantError(f"BLE error: {err}") from err
            finally:
                await self._disconnect_locked()

    async def _read_ps_notify_once(
        self,
        client: BleakClient,
        notify_uuid: str,
        write_uuid: str,
        payload: bytes,
        *,
        timeout: float,
        pre_write_delay: float,
        write_with_response: bool = True,
    ) -> PSState | None:
        acc = bytearray()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[PSState] = loop.create_future()

        def _handler(_sender: Any, data: bytearray) -> None:
            acc.extend(data)
            parsed = parse_config_params_ps_state(bytes(acc))
            if parsed is not None and not fut.done():
                fut.set_result(parsed)

        await client.start_notify(notify_uuid, _handler)
        try:
            await asyncio.sleep(pre_write_delay)
            await client.write_gatt_char(
                write_uuid, payload, response=write_with_response
            )
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            try:
                await client.stop_notify(notify_uuid)
            except BleakError:
                _LOGGER.debug("stop_notify after PS read (ignored)", exc_info=True)

    async def _read_status_probe_locked(
        self, client: BleakClient
    ) -> tuple[bytes | None, bytes | None]:
        ffc: bytes | None = None
        ffd: bytes | None = None
        try:
            raw = await asyncio.wait_for(
                client.read_gatt_char(GET_STATUS_READ_UUID),
                timeout=_GATT_READ_PROBE_TIMEOUT,
            )
            ffc = bytes(raw) if raw else None
        except (BleakError, asyncio.TimeoutError):
            _LOGGER.debug("GATT read fffc failed", exc_info=True)
        try:
            raw = await asyncio.wait_for(
                client.read_gatt_char(INTERNAL_PARAMS_READ_UUID),
                timeout=_GATT_READ_PROBE_TIMEOUT,
            )
            ffd = bytes(raw) if raw else None
        except (BleakError, asyncio.TimeoutError):
            _LOGGER.debug("GATT read fffd failed", exc_info=True)
        return (ffc, ffd)

    def _ps_strategies(self) -> list[tuple[str, str, bytes, str, bool]]:
        req = build_config_params_read_request()
        all_s: list[tuple[str, str, bytes, str, bool]] = [
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_READ_UUID,
                req,
                "notify=fffa write=fffa rsp=True",
                True,
            ),
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_WRITE_UUID,
                req,
                "notify=fffa write=fff9 rsp=True",
                True,
            ),
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_READ_UUID,
                req,
                "notify=fffa write=fffa rsp=False",
                False,
            ),
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_WRITE_UUID,
                req,
                "notify=fffa write=fff9 rsp=False",
                False,
            ),
        ]
        return all_s[:_PS_MAX_STRATEGIES]

    async def _read_ps_state_locked(
        self,
        client: BleakClient,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
    ) -> PSState | None:
        per = timeout if timeout is not None else _PS_READ_PER_STRATEGY_TIMEOUT
        for notify_u, write_u, payload, label, rsp in self._ps_strategies():
            try:
                got = await self._read_ps_notify_once(
                    client,
                    notify_u,
                    write_u,
                    payload,
                    timeout=per,
                    pre_write_delay=pre_write_delay,
                    write_with_response=rsp,
                )
                if got is not None:
                    _LOGGER.debug("PS_State read ok (%s)", label)
                    return got
            except BleakError as err:
                _LOGGER.debug(
                    "PS_State strategy %s BLE error: %s", label, err, exc_info=True
                )
                return None
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "PS_State strategy %s failed: %s", label, err, exc_info=True
                )
        _throttled_ps_fail_warning(
            "Maytronics Dolphin: PS_State read failed (power/FFF8 commands may still work)."
        )
        return None

    async def async_poll_robot_state(
        self,
    ) -> tuple[PSState | None, bytes | None, bytes | None]:
        include_probe = bool(self._options().get(OPT_DIAGNOSTIC_PROBE, False))
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError) as err:
                _LOGGER.debug("poll: could not connect: %s", err)
                return (None, None, None)
            try:
                ps = await self._read_ps_state_locked(client)
                ffc, ffd = (None, None)
                if include_probe:
                    ffc, ffd = await self._read_status_probe_locked(client)
                return (ps, ffc, ffd)
            finally:
                await self._disconnect_locked()

    async def async_read_ps_state(
        self,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
    ) -> PSState | None:
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError) as err:
                _LOGGER.debug("PS_State read: could not connect: %s", err)
                return None
            try:
                return await self._read_ps_state_locked(
                    client, timeout=timeout, pre_write_delay=pre_write_delay
                )
            finally:
                await self._disconnect_locked()

    async def async_read_status_probe(self) -> tuple[bytes | None, bytes | None]:
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError):
                return (None, None)
            try:
                return await self._read_status_probe_locked(client)
            finally:
                await self._disconnect_locked()

    async def async_reconnect(self) -> None:
        """Release BLE (same as app disconnecting) — does not open a new session."""
        if self._shutting_down:
            self._shutting_down = False
        await self.async_release_ble_link()


async def async_ble_periodic_release(hass: HomeAssistant, entry_id: str) -> None:
    """Periodically disconnect so HA never holds the robot hostage."""
    try:
        while True:
            entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
            session: DolphinBleConnection | None = (
                entry_data.get(DATA_BLE_SESSION) if entry_data else None
            )
            if session is None or session._shutting_down:
                return
            entry = hass.config_entries.async_get_entry(entry_id)
            interval = (
                int(get_integration_options(entry)[OPT_BLE_KEEPALIVE_SEC])
                if entry
                else 0
            )
            if interval <= 0:
                await asyncio.sleep(60)
                continue
            await asyncio.sleep(interval)
            if session.is_connected:
                _LOGGER.debug(
                    "Maytronics Dolphin: periodic BLE release (%ss)", interval
                )
            await session.async_release_ble_link()
    except asyncio.CancelledError:
        raise
