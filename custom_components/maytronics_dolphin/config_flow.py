"""Config flow for Maytronics Dolphin BLE."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    DEFAULT_NAME,
    DOMAIN,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_BLE_PERSISTENT_SESSION,
    OPT_DIAGNOSTIC_PROBE,
    OPT_RECONNECT_BUTTON,
    OPT_STATE_POLL_SEC,
)
from .options import get_integration_options

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$")


class MaytronicsDolphinConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Prompt for MAC and optional name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip()
            if not _MAC_RE.match(address):
                errors["base"] = "invalid_mac"
            else:
                address_fmt = dr.format_mac(address)
                await self.async_set_unique_id(address_fmt)
                self._abort_if_unique_id_configured()

                name = (user_input.get(CONF_NAME) or "").strip() or DEFAULT_NAME
                return self.async_create_entry(
                    title=name,
                    data={CONF_ADDRESS: address_fmt, CONF_NAME: name},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        autocomplete="off",
                    )
                ),
                vol.Optional(CONF_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Options under Settings → Devices & services → Configure."""
        return MaytronicsDolphinOptionsFlow()


class MaytronicsDolphinOptionsFlow(config_entries.OptionsFlow):
    """BLE release interval, poll interval, optional buttons."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = get_integration_options(self.config_entry)
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_BLE_KEEPALIVE_SEC,
                    default=current[OPT_BLE_KEEPALIVE_SEC],
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=600,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    OPT_STATE_POLL_SEC,
                    default=current[OPT_STATE_POLL_SEC],
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=600,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    OPT_RECONNECT_BUTTON,
                    default=current[OPT_RECONNECT_BUTTON],
                ): selector.BooleanSelector(),
                vol.Required(
                    OPT_DIAGNOSTIC_PROBE,
                    default=current[OPT_DIAGNOSTIC_PROBE],
                ): selector.BooleanSelector(),
                vol.Required(
                    OPT_BLE_PERSISTENT_SESSION,
                    default=current[OPT_BLE_PERSISTENT_SESSION],
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
