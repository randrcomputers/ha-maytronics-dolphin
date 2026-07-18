"""Poll ``system_status`` for power / cleaning state."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .connection import DolphinPlusBleConnection
from .const import (
    DOMAIN,
    OPT_STATE_POLL_SEC,
    POWER_CONFIRM_ATTEMPTS,
    POWER_CONFIRM_DELAY_SEC,
    POWER_CONFIRM_INITIAL_DELAY_SEC,
)
from .options import get_integration_options
from .protocol import PowerState, sm_state_implies_power_on, sm_state_to_power_state

_LOGGER = logging.getLogger(__name__)


class DolphinPlusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Periodic ``system_status`` poll over local BLE."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: DolphinPlusBleConnection,
        entry: ConfigEntry,
    ) -> None:
        poll_sec = int(get_integration_options(entry)[OPT_STATE_POLL_SEC])
        interval = None if poll_sec <= 0 else timedelta(seconds=poll_sec)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=interval)
        self._session = session
        self._entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        prev = self.data or {}

        if self._session.command_active:
            _LOGGER.debug("Dolphin Plus: deferring poll (command active)")
            return dict(prev)

        try:
            status = await self._session.async_read_system_status()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Dolphin Plus coordinator update failed: %s", err)
            merged = dict(prev)
            merged["poll_ok"] = False
            return merged

        if status is None:
            merged = dict(prev)
            merged["poll_ok"] = False
            return merged

        sm = status.get("sm_state")
        power = sm_state_to_power_state(sm if isinstance(sm, int) else None)
        return {
            "poll_ok": True,
            "sm_state": sm,
            "mu_state": status.get("mu_state"),
            "cleaning_mode": status.get("cleaning_mode"),
            "power_state": power,
            "power_on": sm_state_implies_power_on(sm if isinstance(sm, int) else None),
        }

    async def async_refresh_until_power(
        self,
        expected_on: bool,
        *,
        attempts: int = POWER_CONFIRM_ATTEMPTS,
        delay_sec: float = POWER_CONFIRM_DELAY_SEC,
    ) -> bool:
        for attempt in range(max(1, attempts)):
            if attempt == 0:
                await asyncio.sleep(POWER_CONFIRM_INITIAL_DELAY_SEC)
            elif attempt > 0:
                await asyncio.sleep(delay_sec)
            try:
                status = await self._session.async_read_system_status()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Dolphin Plus power confirm failed: %s", err)
                status = None
            if not status:
                continue
            sm = status.get("sm_state")
            inferred = sm_state_implies_power_on(sm if isinstance(sm, int) else None)
            if inferred is None:
                continue
            if inferred == expected_on:
                self.async_set_updated_data(
                    {
                        "poll_ok": True,
                        "sm_state": sm,
                        "mu_state": status.get("mu_state"),
                        "cleaning_mode": status.get("cleaning_mode"),
                        "power_state": PowerState.ON if expected_on else PowerState.OFF,
                        "power_on": expected_on,
                    }
                )
                return True
        return False
