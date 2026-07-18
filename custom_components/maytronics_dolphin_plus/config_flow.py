"""Config flow for Maytronics Dolphin Plus (local BLE)."""

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
    CONF_PROFILE,
    CONF_TRANSPORT,
    DEFAULT_IOT_GATT_BACKEND,
    DEFAULT_NAME,
    DEFAULT_PROFILE,
    DEFAULT_TRANSPORT,
    DOMAIN,
    IOT_GATT_BACKEND_AUTO,
    IOT_GATT_BACKEND_BLUEZ,
    IOT_GATT_BACKEND_ESPHOME,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_ESPHOME_DEVICE,
    OPT_IOT_GATT_BACKEND,
    OPT_STATE_POLL_SEC,
    PROFILE_BUOY,
    PROFILE_IOT,
    PROFILE_POP,
    TRANSPORT_AUTO,
    TRANSPORT_IOT_GATT,
    TRANSPORT_NUS,
    TRANSPORT_POP,
)
from .iot_gatt_esphome import async_resolve_esphome_notify_service
from .options import get_integration_options

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$")


class MaytronicsDolphinPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return MaytronicsDolphinPlusOptionsFlow()

    def _transport_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    CONF_TRANSPORT,
                    default=defaults.get(CONF_TRANSPORT, DEFAULT_TRANSPORT),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=TRANSPORT_AUTO,
                                label="Auto-detect (IoT GATT → NUS → POP)",
                            ),
                            selector.SelectOptionDict(
                                value=TRANSPORT_IOT_GATT,
                                label="IoT GATT only (fd5abba0 — IoT230 / E35i PS)",
                            ),
                            selector.SelectOptionDict(
                                value=TRANSPORT_NUS,
                                label="Nordic UART only (6E400001 — Triton PS Plus)",
                            ),
                            selector.SelectOptionDict(
                                value=TRANSPORT_POP,
                                label="POP UART only (fd5abca0)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow changing BLE transport without re-adding the device."""
        reconfigure_entry = self._get_reconfigure_entry()
        if user_input is not None:
            data = dict(reconfigure_entry.data)
            data[CONF_TRANSPORT] = user_input[CONF_TRANSPORT]
            return self.async_update_reload_and_abort(
                reconfigure_entry, data=data, reason="reconfigure_successful"
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._transport_schema(dict(reconfigure_entry.data)),
            description_placeholders={
                "version": "0.1.3",
                "current": reconfigure_entry.data.get(
                    CONF_TRANSPORT, DEFAULT_TRANSPORT
                ),
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                    data={
                        CONF_ADDRESS: address_fmt,
                        CONF_NAME: name,
                        CONF_PROFILE: user_input.get(CONF_PROFILE, DEFAULT_PROFILE),
                        CONF_TRANSPORT: user_input.get(
                            CONF_TRANSPORT, DEFAULT_TRANSPORT
                        ),
                    },
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
                vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=PROFILE_IOT, label="IoT / PS Plus (recommended)"
                            ),
                            selector.SelectOptionDict(
                                value=PROFILE_POP, label="POP cordless (experimental)"
                            ),
                            selector.SelectOptionDict(
                                value=PROFILE_BUOY, label="Buoy (experimental)"
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_TRANSPORT, default=DEFAULT_TRANSPORT): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=TRANSPORT_AUTO,
                                label="Auto-detect (IoT GATT → NUS → POP)",
                            ),
                            selector.SelectOptionDict(
                                value=TRANSPORT_IOT_GATT,
                                label="IoT GATT (fd5abba0 — IoT230 / E35i PS)",
                            ),
                            selector.SelectOptionDict(
                                value=TRANSPORT_NUS,
                                label="Nordic UART (6E400001 — Triton PS Plus)",
                            ),
                            selector.SelectOptionDict(
                                value=TRANSPORT_POP,
                                label="POP UART (fd5abca0)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class MaytronicsDolphinPlusOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            backend = user_input.get(OPT_IOT_GATT_BACKEND, DEFAULT_IOT_GATT_BACKEND)
            esphome_device = user_input.get(OPT_ESPHOME_DEVICE)
            if backend == IOT_GATT_BACKEND_ESPHOME and not esphome_device:
                errors["base"] = "esphome_device_required"
            elif esphome_device and not async_resolve_esphome_notify_service(
                self.hass, esphome_device
            ):
                errors["base"] = "esphome_notify_missing"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = get_integration_options(self.config_entry)
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_IOT_GATT_BACKEND,
                    default=current.get(OPT_IOT_GATT_BACKEND, DEFAULT_IOT_GATT_BACKEND),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=IOT_GATT_BACKEND_AUTO,
                                label="Auto (BlueZ dongle, then ESPHome proxy)",
                            ),
                            selector.SelectOptionDict(
                                value=IOT_GATT_BACKEND_BLUEZ,
                                label="Local BlueZ GATT server (USB / built-in BT)",
                            ),
                            selector.SelectOptionDict(
                                value=IOT_GATT_BACKEND_ESPHOME,
                                label="ESPHome proxy GATT server",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    OPT_ESPHOME_DEVICE,
                    description={
                        "suggested_value": current.get(OPT_ESPHOME_DEVICE),
                    },
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        filter=selector.DeviceFilter(integration="esphome"),
                    )
                ),
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
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
