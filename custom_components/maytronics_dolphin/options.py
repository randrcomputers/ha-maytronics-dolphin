"""Config-entry options (BLE keepalive, poll interval, reconnect button)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import (
    BLE_SESSION_KEEPALIVE_INTERVAL_SEC,
    DOLPHIN_STATE_POLL_INTERVAL_SEC,
    OPT_BLE_KEEPALIVE_SEC,
    OPT_BLE_PERSISTENT_SESSION,
    OPT_DIAGNOSTIC_PROBE,
    OPT_RECONNECT_BUTTON,
    OPT_STATE_POLL_SEC,
)

DEFAULT_RECONNECT_BUTTON = True


def get_integration_options(entry: ConfigEntry) -> dict[str, int | bool]:
    """Merged options with the same defaults as pre-options releases."""
    opts = entry.options
    keepalive = opts.get(OPT_BLE_KEEPALIVE_SEC, BLE_SESSION_KEEPALIVE_INTERVAL_SEC)
    poll = opts.get(OPT_STATE_POLL_SEC, DOLPHIN_STATE_POLL_INTERVAL_SEC)
    reconnect = opts.get(OPT_RECONNECT_BUTTON, DEFAULT_RECONNECT_BUTTON)
    probe = opts.get(OPT_DIAGNOSTIC_PROBE, False)
    persistent = opts.get(OPT_BLE_PERSISTENT_SESSION, False)
    return {
        OPT_BLE_KEEPALIVE_SEC: max(0, min(600, int(keepalive))),
        OPT_BLE_PERSISTENT_SESSION: bool(persistent),
        OPT_STATE_POLL_SEC: max(0, min(600, int(poll))),
        OPT_RECONNECT_BUTTON: bool(reconnect),
        OPT_DIAGNOSTIC_PROBE: bool(probe),
    }
