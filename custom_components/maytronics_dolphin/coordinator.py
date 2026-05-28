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
from .status_params import CleaningSurface, InternalParamsSnapshot, WorkingStatus
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

    def _finalize_payload(
        self,
        payload: dict[str, Any],
        *,
        raw_working: WorkingStatus | None = None,
        update_tracker: bool = True,
    ) -> dict[str, Any]:
        ps: PSState | None = payload.get("ps_state")
        if update_tracker:
            stable = self._working_tracker.update(raw_working, ps)
            payload["working_status_raw"] = raw_working
        else:
            stable = self._working_tracker.stable
            payload.setdefault("working_status_raw", None)
        payload["working_status"] = stable
        payload["working_status_held"] = self._working_tracker.is_held
        if stable is not None and payload.get("cleaning_surface") is not None:
            from .status_params import infer_cleaning_surface

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
            should_full_poll = (self._responsive_tick % full_every) == 0 or prev_ps is None
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
                    effective_ps = ps if ps is not None else prev_ps
                    return self._finalize_payload(
                        {
                            "ps_state": effective_ps,
                            "ps_poll_ok": ps is not None,
                            "clean_mode": prev_clean,
                            "clean_mode_poll_ok": prev.get("clean_mode_poll_ok", False),
                            "cleaning_surface": prev_surface,
                            "internal_poll_ok": prev.get("internal_poll_ok", False),
                            "internal_snapshot": prev_internal,
                            "status_fffc_hex": prev_fffc,
                            "internal_fffd_hex": prev_fffd,
                        },
                        update_tracker=False,
                    )

        try:
            ps, clean_mode, surface, working, internal, fffc_raw, fffd_raw = (
                await self._session.async_poll_robot_state()
            )
            return self._finalize_payload(
                {
                    "ps_state": ps,
                    "ps_poll_ok": ps is not None,
                    "clean_mode": clean_mode,
                    "clean_mode_poll_ok": clean_mode is not None,
                    "cleaning_surface": surface,
                    "internal_poll_ok": internal is not None,
                    "internal_snapshot": internal,
                    "status_fffc_hex": fffc_raw.hex() if fffc_raw else prev_fffc,
                    "internal_fffd_hex": fffd_raw.hex() if fffd_raw else prev_fffd,
                },
                raw_working=working,
            )
        except Exception as err:  # noqa: BLE001 — keep last values
            _LOGGER.debug("Maytronics Dolphin coordinator update failed: %s", err)
            return self._finalize_payload(
                {
                    "ps_state": prev_ps,
                    "ps_poll_ok": False,
                    "clean_mode": prev_clean,
                    "clean_mode_poll_ok": False,
                    "cleaning_surface": prev_surface,
                    "internal_poll_ok": False,
                    "internal_snapshot": prev_internal,
                    "status_fffc_hex": prev_fffc,
                    "internal_fffd_hex": prev_fffd,
                },
                raw_working=None,
            )
