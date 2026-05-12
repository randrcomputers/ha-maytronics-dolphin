"""Poll robot ``PS_State`` via ``ConfigParamsRead`` so HA matches physical power."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_params import PSState
from .connection import DolphinBleConnection
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PS_POLL_INTERVAL = timedelta(seconds=45)


class DolphinCoordinator(DataUpdateCoordinator[dict[str, PSState | None]]):
    """Periodic ``ConfigParamsRead`` (PS_State) while BLE session is used."""

    def __init__(self, hass: HomeAssistant, session: DolphinBleConnection) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=PS_POLL_INTERVAL,
        )
        self._session = session

    async def _async_update_data(self) -> dict[str, PSState | None]:
        prev = (self.data or {}).get("ps_state")
        try:
            ps = await self._session.async_read_ps_state()
            return {"ps_state": ps}
        except Exception as err:  # noqa: BLE001 — keep last value, stay available
            _LOGGER.debug("Maytronics Dolphin PS_State poll failed: %s", err)
            return {"ps_state": prev}
