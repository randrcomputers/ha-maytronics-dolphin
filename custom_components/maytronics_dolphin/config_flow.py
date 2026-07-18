"""Config flow for Maytronics Dolphin BLE."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .ble import (
    async_list_discovered_dolphins,
    dolphin_identity_hex,
    is_mydolphin_service_info,
)
from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    DEFAULT_NAME,
    DOMAIN,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_BLE_PERSISTENT_SESSION,
    OPT_DIAGNOSTIC_PROBE,
    OPT_RESPONSIVE_MODE,
    OPT_RECONNECT_BUTTON,
    OPT_STATE_POLL_SEC,
)
from .options import get_integration_options

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$")
_MANUAL_ENTRY = "manual"


def _discovery_unique_id(si: BluetoothServiceInfoBleak) -> str:
    """Prefer 12-hex local-name identity; fall back to on-air MAC."""
    identity = dolphin_identity_hex(si)
    if identity:
        # Format as MAC-style for consistent unique_id display/storage.
        return dr.format_mac(":".join(identity[i : i + 2] for i in range(0, 12, 2)))
    return dr.format_mac(si.address)


def _discovery_title(si: BluetoothServiceInfoBleak) -> str:
    name = (si.name or "").strip()
    if name:
        return name
    return dr.format_mac(si.address)


class MaytronicsDolphinConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow with BLE discovery + manual MAC."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick a discovered FFF0 device, or fall through to manual MAC."""
        errors: dict[str, str] = {}
        current_ids = self._async_current_ids(include_ignore=False)

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == _MANUAL_ENTRY:
                return await self.async_step_manual()
            address_fmt = dr.format_mac(address)
            si = self._discovered.get(address_fmt)
            unique = _discovery_unique_id(si) if si else address_fmt
            await self.async_set_unique_id(unique, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            name = _discovery_title(si) if si else DEFAULT_NAME
            # Always store the on-air BD_ADDR HA uses for connections.
            connect_addr = address_fmt
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: connect_addr, CONF_NAME: name},
            )

        self._discovered.clear()
        seen_identities: set[str] = set()
        for si in async_list_discovered_dolphins(self.hass, connectable=True):
            unique = _discovery_unique_id(si)
            address = dr.format_mac(si.address)
            if unique in current_ids or unique in seen_identities:
                continue
            if address in self._discovered:
                continue
            seen_identities.add(unique)
            self._discovered[address] = si
        # Also scan non-connectable cache (some proxies populate this first).
        for si in async_discovered_service_info(self.hass, connectable=False):
            if not is_mydolphin_service_info(si):
                continue
            unique = _discovery_unique_id(si)
            address = dr.format_mac(si.address)
            if unique in current_ids or unique in seen_identities:
                continue
            if address in self._discovered:
                continue
            seen_identities.add(unique)
            self._discovered[address] = si

        if not self._discovered:
            return await self.async_step_manual()

        options = {
            address: f"{_discovery_title(si)} ({address})"
            for address, si in self._discovered.items()
        }
        options[_MANUAL_ENTRY] = "Enter MAC address manually…"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
            errors=errors,
        )

    async def async_step_manual(
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
                await self.async_set_unique_id(address_fmt, raise_on_progress=False)
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
        return self.async_show_form(
            step_id="manual", data_schema=schema, errors=errors
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a Bluetooth discovery advertisement."""
        if not is_mydolphin_service_info(discovery_info):
            return self.async_abort(reason="not_supported")

        unique = _discovery_unique_id(discovery_info)
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": _discovery_title(discovery_info),
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a single discovered device."""
        assert self._discovery_info is not None
        if user_input is not None:
            address = dr.format_mac(self._discovery_info.address)
            name = _discovery_title(self._discovery_info) or DEFAULT_NAME
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: address, CONF_NAME: name},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": _discovery_title(self._discovery_info),
            },
        )

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
                vol.Required(
                    OPT_RESPONSIVE_MODE,
                    default=current[OPT_RESPONSIVE_MODE],
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
