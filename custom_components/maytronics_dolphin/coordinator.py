"""Poll robot ``PS_State`` and optional GATT diagnostics."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_params import PSState
from .connection import DolphinBleConnection
from .const import DOMAIN, OPT_STATE_POLL_SEC
from .options import get_integration_options

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

    async def _async_update_data(self) -> dict[str, Any]:
        prev = self.data or {}
        prev_ps: PSState | None = prev.get("ps_state")
        prev_fffc = prev.get("status_fffc_hex")
        prev_fffd = prev.get("internal_fffd_hex")
        try:
            ps, fffc_raw, fffd_raw = await self._session.async_poll_robot_state()
            return {
                "ps_state": ps,
                "ps_poll_ok": ps is not None,
                "status_fffc_hex": fffc_raw.hex() if fffc_raw else prev_fffc,
                "internal_fffd_hex": fffd_raw.hex() if fffd_raw else prev_fffd,
            }
        except Exception as err:  # noqa: BLE001 — keep last values
            _LOGGER.debug("Maytronics Dolphin coordinator update failed: %s", err)
            return {
                "ps_state": prev_ps,
                "ps_poll_ok": False,
                "status_fffc_hex": prev_fffc,
                "internal_fffd_hex": prev_fffd,
            }
