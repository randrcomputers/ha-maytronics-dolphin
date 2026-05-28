"""BLE client for Maytronics Dolphin — short sessions (connect, work, disconnect).

Holding an idle GATT link wedges some robots (BT LED stays on, unit frozen until
power cycle). We release the link after every command and poll.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ble import _noop_notify, async_resolve_ble_device
from .config_params import (
    CONFIG_PARAMS_CMD_PS_STATE,
    CONFIG_PARAMS_CMD_WORKING_CLEAN_MODE,
    CleanMode,
    PSState,
    build_config_params_read_request,
    parse_config_params_clean_mode,
    parse_config_params_ps_state,
)

_T = TypeVar("_T")
from .const import (
    CONFIG_PARAMS_READ_UUID,
    CONFIG_PARAMS_WRITE_UUID,
    DATA_BLE_SESSION,
    DOMAIN,
    GET_STATUS_READ_UUID,
    INTERNAL_PARAMS_READ_UUID,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_BLE_PERSISTENT_SESSION,
    OPT_DIAGNOSTIC_PROBE,
    WORKING_STATUS_RETRY_DELAY_SEC,
)
from .status_params import (
    CleaningSurface,
    InternalParamsSnapshot,
    WorkingStatus,
    build_get_status_read_request,
    build_internal_params_read_request,
    infer_cleaning_surface,
    parse_get_status_working,
    parse_internal_params_snapshot,
    resolve_working_status,
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

    def _persistent_session(self) -> bool:
        return bool(self._options().get(OPT_BLE_PERSISTENT_SESSION))

    async def _release_after_operation_locked(self, *, force: bool = False) -> None:
        """Disconnect after an operation unless persistent session is enabled."""
        if force or not self._persistent_session():
            await self._disconnect_locked()

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
        mode = "persistent" if self._persistent_session() else "ephemeral"
        _LOGGER.debug(
            "Maytronics Dolphin: BLE connected (%s, %s)",
            ble_device.address,
            mode,
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
                await self._release_after_operation_locked(force=True)
                raise HomeAssistantError(f"BLE error: {err}") from err
            finally:
                await self._release_after_operation_locked()

    async def _read_config_params_notify_once(
        self,
        client: BleakClient,
        notify_uuid: str,
        write_uuid: str,
        payload: bytes,
        parser: Callable[[bytes], _T | None],
        *,
        timeout: float,
        pre_write_delay: float,
        write_with_response: bool = True,
    ) -> _T | None:
        acc = bytearray()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[_T] = loop.create_future()

        def _handler(_sender: Any, data: bytearray) -> None:
            acc.extend(data)
            parsed = parser(bytes(acc))
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

    def _config_params_strategies(
        self, command_code: int
    ) -> list[tuple[str, str, bytes, str, bool]]:
        req = build_config_params_read_request(command_code)
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

    async def _read_config_params_locked(
        self,
        client: BleakClient,
        command_code: int,
        parser: Callable[[bytes], _T | None],
        log_label: str,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
        warn_on_fail: bool = True,
    ) -> _T | None:
        per = timeout if timeout is not None else _PS_READ_PER_STRATEGY_TIMEOUT
        for notify_u, write_u, payload, label, rsp in self._config_params_strategies(
            command_code
        ):
            try:
                got = await self._read_config_params_notify_once(
                    client,
                    notify_u,
                    write_u,
                    payload,
                    parser,
                    timeout=per,
                    pre_write_delay=pre_write_delay,
                    write_with_response=rsp,
                )
                if got is not None:
                    _LOGGER.debug("%s read ok (%s)", log_label, label)
                    return got
            except BleakError as err:
                _LOGGER.debug(
                    "%s strategy %s BLE error: %s", log_label, label, err, exc_info=True
                )
                return None
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "%s strategy %s failed: %s", log_label, label, err, exc_info=True
                )
        if warn_on_fail:
            _throttled_ps_fail_warning(
                f"Maytronics Dolphin: {log_label} read failed (other BLE commands may still work)."
            )
        return None

    async def _read_ps_state_locked(
        self,
        client: BleakClient,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
    ) -> PSState | None:
        return await self._read_config_params_locked(
            client,
            CONFIG_PARAMS_CMD_PS_STATE,
            parse_config_params_ps_state,
            "PS_State",
            timeout=timeout,
            pre_write_delay=pre_write_delay,
        )

    async def _read_clean_mode_locked(
        self,
        client: BleakClient,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
    ) -> CleanMode | None:
        return await self._read_config_params_locked(
            client,
            CONFIG_PARAMS_CMD_WORKING_CLEAN_MODE,
            parse_config_params_clean_mode,
            "Working_Clean_Mode",
            timeout=timeout,
            pre_write_delay=pre_write_delay,
            warn_on_fail=False,
        )

    async def _read_gatt_notify_locked(
        self,
        client: BleakClient,
        notify_uuid: str,
        write_uuid: str,
        payload: bytes,
        parser: Callable[[bytes], _T | None],
        log_label: str,
        *,
        timeout: float | None = None,
        pre_write_delay: float = 0.2,
    ) -> _T | None:
        per = timeout if timeout is not None else _PS_READ_PER_STRATEGY_TIMEOUT
        strategies = (
            (notify_uuid, notify_uuid, True),
            (notify_uuid, CONFIG_PARAMS_WRITE_UUID, True),
            (notify_uuid, notify_uuid, False),
        )
        for notify_u, write_u, rsp in strategies:
            try:
                got = await self._read_config_params_notify_once(
                    client,
                    notify_u,
                    write_u,
                    payload,
                    parser,
                    timeout=per,
                    pre_write_delay=pre_write_delay,
                    write_with_response=rsp,
                )
                if got is not None:
                    _LOGGER.debug("%s read ok (notify=%s write=%s)", log_label, notify_u, write_u)
                    return got
            except BleakError as err:
                _LOGGER.debug("%s BLE error: %s", log_label, err, exc_info=True)
                return None
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("%s failed: %s", log_label, err, exc_info=True)
        return None

    async def _read_internal_params_locked(
        self,
        client: BleakClient,
    ) -> InternalParamsSnapshot | None:
        snap = await self._read_gatt_notify_locked(
            client,
            INTERNAL_PARAMS_READ_UUID,
            INTERNAL_PARAMS_READ_UUID,
            build_internal_params_read_request(),
            parse_internal_params_snapshot,
            "InternalParamsRead",
        )
        if snap:
            _LOGGER.debug(
                "InternalParams: clean=%s climb=%s phase=%s motor=%s",
                snap.clean_mode_byte,
                snap.climb_every,
                snap.phase_byte,
                snap.motor_aux,
            )
        return snap

    async def _read_get_status_locked(
        self, client: BleakClient
    ) -> WorkingStatus | None:
        working = await self._read_gatt_notify_locked(
            client,
            GET_STATUS_READ_UUID,
            GET_STATUS_READ_UUID,
            build_get_status_read_request(),
            parse_get_status_working,
            "GetStatusRead",
        )
        if working is not None:
            return working
        try:
            raw = await asyncio.wait_for(
                client.read_gatt_char(GET_STATUS_READ_UUID),
                timeout=_GATT_READ_PROBE_TIMEOUT,
            )
            if raw:
                return parse_get_status_working(bytes(raw))
        except (BleakError, asyncio.TimeoutError):
            _LOGGER.debug("GetStatusRead plain GATT read failed", exc_info=True)
        return None

    async def async_poll_robot_state(
        self,
    ) -> tuple[
        PSState | None,
        CleanMode | None,
        CleaningSurface | None,
        WorkingStatus | None,
        InternalParamsSnapshot | None,
        bytes | None,
        bytes | None,
    ]:
        include_probe = bool(self._options().get(OPT_DIAGNOSTIC_PROBE, False))
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError) as err:
                _LOGGER.debug("poll: could not connect: %s", err)
                await self._release_after_operation_locked(force=True)
                return (None, None, None, None, None, None, None)
            try:
                ps = await self._read_ps_state_locked(client)
                clean_mode = await self._read_clean_mode_locked(client)
                internal: InternalParamsSnapshot | None = None
                working: WorkingStatus | None = None
                if ps is not None and ps != PSState.OFF:
                    internal = await self._read_internal_params_locked(client)
                    gatt_working = await self._read_get_status_locked(client)
                    working = resolve_working_status(ps, gatt_working, internal)
                    if working in (None, WorkingStatus.UNKNOWN):
                        await asyncio.sleep(WORKING_STATUS_RETRY_DELAY_SEC)
                        gatt_working = await self._read_get_status_locked(client)
                        if internal is None:
                            internal = await self._read_internal_params_locked(client)
                        retry = resolve_working_status(ps, gatt_working, internal)
                        if retry not in (None, WorkingStatus.UNKNOWN):
                            working = retry
                else:
                    working = None
                surface = infer_cleaning_surface(
                    ps, clean_mode, internal, working=working
                )
                ffc, ffd = (None, None)
                if include_probe:
                    ffc, ffd = await self._read_status_probe_locked(client)
                return (ps, clean_mode, surface, working, internal, ffc, ffd)
            except BleakError:
                await self._release_after_operation_locked(force=True)
                raise
            finally:
                await self._release_after_operation_locked()

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
                await self._release_after_operation_locked(force=True)
                return None
            try:
                return await self._read_ps_state_locked(
                    client, timeout=timeout, pre_write_delay=pre_write_delay
                )
            except BleakError:
                await self._release_after_operation_locked(force=True)
                raise
            finally:
                await self._release_after_operation_locked()

    async def async_read_status_probe(self) -> tuple[bytes | None, bytes | None]:
        async with self._lock:
            try:
                client = await self._ensure_connected_locked()
            except (BleakError, HomeAssistantError):
                return (None, None)
            try:
                return await self._read_status_probe_locked(client)
            except BleakError:
                await self._release_after_operation_locked(force=True)
                raise
            finally:
                await self._release_after_operation_locked()

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
            opts = get_integration_options(entry) if entry else {}
            if opts.get(OPT_BLE_PERSISTENT_SESSION):
                await asyncio.sleep(60)
                continue
            interval = int(opts.get(OPT_BLE_KEEPALIVE_SEC, 0))
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
