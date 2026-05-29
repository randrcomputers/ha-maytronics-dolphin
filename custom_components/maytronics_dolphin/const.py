"""Constants for Maytronics Dolphin BLE control."""

DOMAIN = "maytronics_dolphin"

CONF_ADDRESS = "address"
CONF_NAME = "name"

# From MyDolphin `DolphinData` — all characteristics live under this service.
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"

# `BTCommand.UUID` and neighbors (order confirmed in app dex string pool; verify in jadx if a model misbehaves).
COMMAND_CHAR_UUID = "0000fff8-0000-1000-8000-00805f9b34fb"
# JADX: ``ConfigParamsRead.UUID`` = fffa, ``ConfigParamsWrite.UUID`` = fff9 (not dex string order).
CONFIG_PARAMS_READ_UUID = "0000fffa-0000-1000-8000-00805f9b34fb"
CONFIG_PARAMS_WRITE_UUID = "0000fff9-0000-1000-8000-00805f9b34fb"
FIRMWARE_CHAR_UUID = "0000fffb-0000-1000-8000-00805f9b34fb"  # DolphinData.UPLOAD_BURN_FIRMWARE — avoid writing unless you mean OTA.
GET_STATUS_READ_UUID = "0000fffc-0000-1000-8000-00805f9b34fb"
INTERNAL_PARAMS_READ_UUID = "0000fffd-0000-1000-8000-00805f9b34fb"

GENERAL_CHAR_UUID = "0000fff6-0000-1000-8000-00805f9b34fb"
TEST_CHAR_UUID = "0000fff7-0000-1000-8000-00805f9b34fb"

SOP = 0xAB
POLYNOMIAL = 0xD8  # Java (byte)-40

# 3-byte on-air form used in HCI logs for simple commands.
CMD_STARTUP = 0x07  # Startup_dolphin
CMD_SHUTDOWN = 0x06  # Shutdown_dolphin

DEFAULT_NAME = "Dolphin"

# If the MAC is not in HA's Bluetooth cache yet, wait this long for a connectable
# advertisement before failing (seconds). Helps first button press after HA restart.
BLE_ADVERTISEMENT_WAIT_SECONDS = 25

# Periodic BLE *release* (disconnect if connected). 0 = off. Not a reconnect loop.
BLE_SESSION_KEEPALIVE_INTERVAL_SEC = 120

# Coordinator: PS_State poll interval while integration is loaded.
DOLPHIN_STATE_POLL_INTERVAL_SEC = 45

# Config-entry options (Settings → integration → Configure).
OPT_BLE_KEEPALIVE_SEC = "ble_keepalive_seconds"
OPT_BLE_PERSISTENT_SESSION = "ble_persistent_session_enabled"
OPT_STATE_POLL_SEC = "state_poll_seconds"
OPT_RECONNECT_BUTTON = "reconnect_button_enabled"
OPT_DIAGNOSTIC_PROBE = "diagnostic_probe_enabled"
OPT_RESPONSIVE_MODE = "responsive_mode_enabled"

# Responsive mode (opt-in): lighter, more frequent PS_State polling for "live" feel.
RESPONSIVE_ACTIVE_POLL_SEC = 20
RESPONSIVE_IDLE_POLL_SEC = 75
RESPONSIVE_ACTIVE_FULL_POLL_EVERY = 3
RESPONSIVE_IDLE_FULL_POLL_EVERY = 8

# Working status stabilizer (Phase 1 reliability).
WORKING_STATUS_AT_WORK_HOLD_SEC = 90
WORKING_STATUS_FINISHED_HOLD_SEC = 7200
WORKING_STATUS_UNKNOWN_AFTER_MISSES = 4
WORKING_STATUS_RETRY_DELAY_SEC = 0.35

# Runtime keys (hass.data[DOMAIN][entry_id])
DATA_BLE_SESSION = "ble_session"
DATA_KEEPALIVE_TASK = "keepalive_task"
DATA_COORDINATOR = "coordinator"
DATA_JOY = "joy"
DATA_CARD_SUB = "card_sub"
