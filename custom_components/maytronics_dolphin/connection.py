"""Persistent BLE client for Maytronics Dolphin (one session per config entry)."""

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
)
from .options import get_integration_options

_LOGGER = logging.getLogger(__name__)

_INITIAL_CONNECT_DELAY_SEC = 12.0
_PS_READ_PER_STRATEGY_TIMEOUT = 3.5
_PS_FAIL_LOG_INTERVAL_SEC = 300.0


class _PsFailLogThrottle:
    """Rate-limit ``PS_State`` failure warnings to the HA log."""

    last_monotonic: float = 0.0


def _throttled_ps_fail_warning(message: str) -> None:
    now = time.monotonic()
    if now - _PsFailLogThrottle.last_monotonic >= _PS_FAIL_LOG_INTERVAL_SEC:
        _PsFailLogThrottle.last_monotonic = now
        _LOGGER.warning("%s", message)


class DolphinBleConnection:
    """Keeps a BleakClient open between commands; reconnects after failures."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None

    @property
    def is_connected(self) -> bool:
        """Whether a live BLE link is held (best-effort; not locked)."""
        c = self._client
        return c is not None and c.is_connected

    async def async_disconnect(self) -> None:
        """Disconnect and release the client (e.g. on config entry unload)."""
        async with self._lock:
            await self._disconnect_locked()

    async def _disconnect_locked(self) -> None:
        if self._client is None:
            return
        try:
            if self._client.is_connected:
                await self._client.disconnect()
        except BleakError:
            _LOGGER.debug("disconnect raised BleakError (ignored)", exc_info=True)
        self._client = None

    async def _ensure_connected_locked(self) -> BleakClientWithServiceCache:
        if self._client is not None and self._client.is_connected:
            return self._client

        await self._disconnect_locked()

        ble_device = await async_resolve_ble_device(self.hass, self.address)
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            name=ble_device.name or self.address,
            timeout=60.0,
        )
        if not client.is_connected:
            raise HomeAssistantError("Failed to connect over BLE")
        self._client = client
        _LOGGER.info(
            "Maytronics Dolphin: BLE connected (%s)",
            ble_device.address,
        )
        return self._client

    async def async_send_gatt_packet(
        self,
        payload: bytes,
        char_uuid: str,
        *,
        pre_write_delay: float = 0.3,
        post_write_delay: float = 0.3,
    ) -> None:
        """Run one MyDolphin-style write on the shared connection."""
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
                await self._disconnect_locked()
                raise HomeAssistantError(f"BLE error: {err}") from err

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
        """Subscribe on ``notify_uuid``, write ``write_uuid``, return first parsed PS or timeout."""
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

    async def async_read_ps_state(
        self,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
    ) -> PSState | None:
        """Read PS_State via ``ConfigParamsRead`` (MyDolphin 2.3.19: 3-byte ``getBytes()`` on ``fffa``/``fff9``).

        Notify stays on ``fffa``; some stacks expect the write on ``fff9`` instead.
        Tries GATT write-with-response first, then without response.
        """
        per = timeout if timeout is not None else _PS_READ_PER_STRATEGY_TIMEOUT
        req = build_config_params_read_request()
        strategies: list[tuple[str, str, bytes, str, bool]] = [
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_READ_UUID,
                req,
                "notify=fffa write=fffa len=3 rsp=True",
                True,
            ),
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_WRITE_UUID,
                req,
                "notify=fffa write=fff9 len=3 rsp=True",
                True,
            ),
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_READ_UUID,
                req,
                "notify=fffa write=fffa len=3 rsp=False",
                False,
            ),
            (
                CONFIG_PARAMS_READ_UUID,
                CONFIG_PARAMS_WRITE_UUID,
                req,
                "notify=fffa write=fff9 len=3 rsp=False",
                False,
            ),
        ]
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError) as err:
                _LOGGER.debug("PS_State read: could not connect: %s", err)
                return None
            for notify_u, write_u, payload, label, rsp in strategies:
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
                    await self._disconnect_locked()
                    try:
                        client = await self._ensure_connected_locked()
                    except (BleakError, HomeAssistantError):
                        return None
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug(
                        "PS_State strategy %s failed: %s", label, err, exc_info=True
                    )
            _throttled_ps_fail_warning(
                "Maytronics Dolphin: PS_State notify failed for all BLE strategies "
                "(notify/write UUID or packet length may differ on this model). "
                "Power/FFF8 commands still work. Enable debug logging for "
                "`custom_components.maytronics_dolphin` or capture HCI when the "
                "MyDolphin app reads status."
            )
            return None

    async def async_read_status_probe(self) -> tuple[bytes | None, bytes | None]:
        """Try reads on ``fffc`` / ``fffd`` under one lock (may be unsupported on some models)."""
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError):
                return (None, None)
            ffc: bytes | None = None
            ffd: bytes | None = None
            try:
                raw = await client.read_gatt_char(GET_STATUS_READ_UUID)
                ffc = bytes(raw) if raw else None
            except BleakError:
                _LOGGER.debug("GATT read fffc failed", exc_info=True)
            try:
                raw = await client.read_gatt_char(INTERNAL_PARAMS_READ_UUID)
                ffd = bytes(raw) if raw else None
            except BleakError:
                _LOGGER.debug("GATT read fffd failed", exc_info=True)
            return (ffc, ffd)

    async def async_try_background_connect(self) -> None:
        """Best-effort connect shortly after startup (does not raise)."""
        try:
            async with self._lock:
                await self._ensure_connected_locked()
        except Exception as err:  # noqa: BLE001 — optional probe
            _LOGGER.debug(
                "Maytronics Dolphin background BLE connect skipped: %s",
                err,
            )


async def async_schedule_initial_connect(
    hass: HomeAssistant, entry_id: str
) -> None:
    """Wait for HA Bluetooth to settle, then try one connect (non-blocking)."""
    await asyncio.sleep(_INITIAL_CONNECT_DELAY_SEC)
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry_id)
    if not entry_data:
        return
    session: DolphinBleConnection | None = entry_data.get(DATA_BLE_SESSION)
    if session is None:
        return
    await session.async_try_background_connect()


async def async_ble_session_keepalive(hass: HomeAssistant, entry_id: str) -> None:
    """Periodically ensure BLE session is up (idle links sometimes drop)."""
    try:
        while True:
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
            domain_data = hass.data.get(DOMAIN, {})
            entry_data = domain_data.get(entry_id)
            if not entry_data:
                return
            session: DolphinBleConnection | None = entry_data.get(DATA_BLE_SESSION)
            if session is None:
                return
            await session.async_try_background_connect()
    except asyncio.CancelledError:
        raise
