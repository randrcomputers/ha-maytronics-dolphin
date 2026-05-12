"""Persistent BLE client for Maytronics Dolphin (one session per config entry)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ble import _noop_notify, async_resolve_ble_device
from .config_params import (
    PSState,
    build_config_params_read_request,
    parse_config_params_ps_state,
)
from .const import CONFIG_PARAMS_READ_UUID, DATA_BLE_SESSION, DOMAIN

_LOGGER = logging.getLogger(__name__)

_INITIAL_CONNECT_DELAY_SEC = 12.0


class DolphinBleConnection:
    """Keeps a BleakClient open between commands; reconnects after failures."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self._lock = asyncio.Lock()
        self._client: BleakClient | None = None

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

    async def _ensure_connected_locked(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client

        await self._disconnect_locked()

        ble_device = await async_resolve_ble_device(self.hass, self.address)
        client = BleakClient(ble_device, timeout=60.0)
        await client.connect()
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

    async def async_read_ps_state(
        self,
        *,
        timeout: float = 8.0,
        pre_write_delay: float = 0.15,
    ) -> PSState | None:
        """Write ``ConfigParamsRead`` (PS_State) on ``fffa`` and parse one notify."""
        payload = build_config_params_read_request()
        char_uuid = CONFIG_PARAMS_READ_UUID
        async with self._lock:
            acc = bytearray()
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[PSState] = loop.create_future()
            client: BleakClient | None = None

            def _handler(_sender: Any, data: bytearray) -> None:
                acc.extend(data)
                parsed = parse_config_params_ps_state(bytes(acc))
                if parsed is not None and not fut.done():
                    fut.set_result(parsed)

            try:
                client = await self._ensure_connected_locked()
                await client.start_notify(char_uuid, _handler)
                await asyncio.sleep(pre_write_delay)
                await client.write_gatt_char(char_uuid, payload, response=True)
                return await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                _LOGGER.debug("ConfigParamsRead PS_State notify timeout")
                return None
            except BleakError as err:
                await self._disconnect_locked()
                raise HomeAssistantError(f"BLE error: {err}") from err
            finally:
                if client is not None:
                    try:
                        await client.stop_notify(char_uuid)
                    except BleakError:
                        _LOGGER.debug(
                            "stop_notify after PS read (ignored)", exc_info=True
                        )

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
