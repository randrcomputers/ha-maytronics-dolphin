"""Config flow for Maytronics Dolphin BLE."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import CONF_ADDRESS, CONF_NAME, DEFAULT_NAME, DOMAIN

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
