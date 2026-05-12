"""Constants for Maytronics Dolphin BLE control."""

DOMAIN = "maytronics_dolphin"

CONF_ADDRESS = "address"
CONF_NAME = "name"

# From MyDolphin `DolphinData` — all characteristics live under this service.
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"

# `BTCommand.UUID` and neighbors (order confirmed in app dex string pool; verify in jadx if a model misbehaves).
COMMAND_CHAR_UUID = "0000fff8-0000-1000-8000-00805f9b34fb"
CONFIG_PARAMS_READ_UUID = "0000fff9-0000-1000-8000-00805f9b34fb"
CONFIG_PARAMS_WRITE_UUID = "0000fffa-0000-1000-8000-00805f9b34fb"
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

# Runtime keys (hass.data[DOMAIN][entry_id])
DATA_BLE_LOCK = "ble_lock"
DATA_JOY = "joy"
DATA_CARD_SUB = "card_sub"
