"""Poll robot ``PS_State`` and optional GATT diagnostics."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_params import CleanMode, PSState
from .connection import DolphinBleConnection
from .const import DOMAIN, OPT_STATE_POLL_SEC
from .const import (
    OPT_RESPONSIVE_MODE,
    RESPONSIVE_ACTIVE_FULL_POLL_EVERY,
    RESPONSIVE_ACTIVE_POLL_SEC,
    RESPONSIVE_IDLE_FULL_POLL_EVERY,
    RESPONSIVE_IDLE_POLL_SEC,
)
from .options import get_integration_options
from .status_params import (
    CleaningSurface,
    InternalParamsSnapshot,
    WorkingStatus,
    infer_cleaning_surface,
)
from .status_tracker import WorkingStatusTracker

_LOGGER = logging.getLogger(__name__)


class DolphinCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Periodic ``ConfigParamsRead`` (PS_State) + best-effort ``fffc``/``fffd`` reads."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: DolphinBleConnection,
        entry: ConfigEntry,
    ) -> None:
        poll_sec = int(get_integration_options(entry)[OPT_STATE_POLL_SEC])
        interval = None if poll_sec <= 0 else timedelta(seconds=poll_sec)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=interval,
        )
        self._session = session
        self._entry = entry
        self._responsive_tick = 0
        self._working_tracker = WorkingStatusTracker()

    def _responsive_enabled(self) -> bool:
        return bool(get_integration_options(self._entry).get(OPT_RESPONSIVE_MODE, False))

    def _merge_poll(
        self,
        prev: dict[str, Any],
        *,
        ps: PSState | None,
        clean_mode: CleanMode | None,
        surface: CleaningSurface | None,
        working: WorkingStatus | None,
        internal: InternalParamsSnapshot | None,
        fffc_raw: bytes | None,
        fffd_raw: bytes | None,
    ) -> dict[str, Any]:
        """Keep last good values when a read fails — failed read is not ``off``."""
        prev_ps: PSState | None = prev.get("ps_state")
        if ps is None and prev_ps is not None:
            ps = prev_ps
            ps_poll_ok = False
        else:
            ps_poll_ok = ps is not None

        if clean_mode is None:
            clean_mode = prev.get("clean_mode")
        clean_mode_poll_ok = clean_mode is not None

        internal_fresh = internal is not None
        if internal is None:
            internal = prev.get("internal_snapshot")
        internal_poll_ok = internal_fresh

        prev_surface: CleaningSurface | None = prev.get("cleaning_surface")
        if surface in (None, CleaningSurface.UNAVAILABLE, CleaningSurface.UNKNOWN):
            if (
                ps is not None
                and ps != PSState.OFF
                and prev_surface
                in (
                    CleaningSurface.FLOOR,
                    CleaningSurface.WALL,
                    CleaningSurface.WATERLINE,
                )
            ):
                surface = prev_surface

        if surface is None and prev_surface is not None:
            surface = prev_surface

        return {
            "ps_state": ps,
            "ps_poll_ok": ps_poll_ok,
            "clean_mode": clean_mode,
            "clean_mode_poll_ok": clean_mode_poll_ok,
            "cleaning_surface": surface,
            "internal_poll_ok": internal_poll_ok,
            "internal_snapshot": internal,
            "status_fffc_hex": fffc_raw.hex() if fffc_raw else prev.get("status_fffc_hex"),
            "internal_fffd_hex": fffd_raw.hex() if fffd_raw else prev.get("internal_fffd_hex"),
            "_raw_working": working,
        }

    def _finalize_payload(
        self,
        payload: dict[str, Any],
        *,
        raw_working: WorkingStatus | None = None,
        update_tracker: bool = True,
    ) -> dict[str, Any]:
        if "_raw_working" in payload:
            raw_working = payload.pop("_raw_working")
        ps: PSState | None = payload.get("ps_state")
        if update_tracker:
            stable = self._working_tracker.update(raw_working, ps)
            payload["working_status_raw"] = raw_working
        else:
            stable = self._working_tracker.stable
            payload.setdefault("working_status_raw", None)
        payload["working_status"] = stable
        payload["working_status_held"] = self._working_tracker.is_held
        if ps is not None and ps != PSState.OFF:
            payload["cleaning_surface"] = infer_cleaning_surface(
                ps,
                payload.get("clean_mode"),
                payload.get("internal_snapshot"),
                working=stable,
            )
        return payload

    async def _async_update_data(self) -> dict[str, Any]:
        prev = self.data or {}
        prev_ps: PSState | None = prev.get("ps_state")
        prev_clean: CleanMode | None = prev.get("clean_mode")
        prev_surface: CleaningSurface | None = prev.get("cleaning_surface")
        prev_internal: InternalParamsSnapshot | None = prev.get("internal_snapshot")
        prev_fffc = prev.get("status_fffc_hex")
        prev_fffd = prev.get("internal_fffd_hex")

        if self._responsive_enabled():
            self._responsive_tick += 1
            prev_active = prev_ps is not None and prev_ps != PSState.OFF
            self.update_interval = timedelta(
                seconds=RESPONSIVE_ACTIVE_POLL_SEC
                if prev_active
                else RESPONSIVE_IDLE_POLL_SEC
            )
            full_every = (
                RESPONSIVE_ACTIVE_FULL_POLL_EVERY
                if prev_active
                else RESPONSIVE_IDLE_FULL_POLL_EVERY
            )
            prev_working = prev.get("working_status")
            force_status_while_cleaning = (
                prev_active
                and prev_working == WorkingStatus.AT_WORK
            )
            should_full_poll = (
                (self._responsive_tick % full_every) == 0
                or prev_ps is None
                or force_status_while_cleaning
            )
            if not should_full_poll:
                try:
                    ps = await self._session.async_read_ps_state(
                        timeout=2.8, pre_write_delay=0.1
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug(
                        "Maytronics Dolphin responsive PS_State read failed: %s", err
                    )
                    ps = None

                if ps is not None and ((ps == PSState.OFF) != (prev_ps == PSState.OFF)):
                    should_full_poll = True
                else:
                    merged = self._merge_poll(
                        prev,
                        ps=ps,
                        clean_mode=prev_clean,
                        surface=prev_surface,
                        working=None,
                        internal=prev_internal,
                        fffc_raw=None,
                        fffd_raw=None,
                    )
                    return self._finalize_payload(merged, update_tracker=False)

        try:
            ps, clean_mode, surface, working, internal, fffc_raw, fffd_raw = (
                await self._session.async_poll_robot_state()
            )
            merged = self._merge_poll(
                prev,
                ps=ps,
                clean_mode=clean_mode,
                surface=surface,
                working=working,
                internal=internal,
                fffc_raw=fffc_raw,
                fffd_raw=fffd_raw,
            )
            return self._finalize_payload(merged, raw_working=working)
        except Exception as err:  # noqa: BLE001 — keep last values
            _LOGGER.debug("Maytronics Dolphin coordinator update failed: %s", err)
            merged = self._merge_poll(
                prev,
                ps=None,
                clean_mode=None,
                surface=None,
                working=None,
                internal=None,
                fffc_raw=None,
                fffd_raw=None,
            )
            merged["ps_poll_ok"] = False
            merged["clean_mode_poll_ok"] = False
            merged["internal_poll_ok"] = False
            return self._finalize_payload(merged, raw_working=None)
