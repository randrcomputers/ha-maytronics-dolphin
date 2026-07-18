"""Constants for Maytronics Dolphin Plus (MyDolphin Plus app) local BLE."""

DOMAIN = "maytronics_dolphin_plus"

CONF_ADDRESS = "address"
CONF_NAME = "name"
CONF_PROFILE = "profile"
CONF_TRANSPORT = "transport"

PROFILE_IOT = "iot"
PROFILE_POP = "pop"
PROFILE_BUOY = "buoy"

# Nordic UART (UART_LIBERTY in Plus app 3.4) — default for PS / wired IoT robots.
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Alternate IoT GATT service (some models advertise this instead of NUS).
IOT_SERVICE_UUID = "fd5abba0-3935-11e5-85a6-0002a5d5c51b"
IOT_WRITE_UUID = "fd5abba1-3935-11e5-85a6-0002a5d5c51b"
IOT_NOTIFY_UUID = "fd5abba1-3935-11e5-85a6-0002a5d5c51b"

# POP cordless UART (UART_POP).
POP_SERVICE_UUID = "fd5abca0-3935-11e5-85a6-0002a5d5c51b"
POP_WRITE_UUID = "fd5abca1-3935-11e5-85a6-0002a5d5c51b"
POP_NOTIFY_UUID = "fd5abca2-3935-11e5-85a6-0002a5d5c51b"

TRANSPORT_NUS = "nus"
TRANSPORT_IOT_GATT = "iot_gatt"
TRANSPORT_POP = "pop"
TRANSPORT_AUTO = "auto"

DEFAULT_NAME = "Dolphin Plus"
DEFAULT_PROFILE = PROFILE_IOT
# Plus app defaults new IoT PSUs (E35i / IoT230) to IOT GATT, not Nordic UART.
DEFAULT_TRANSPORT = TRANSPORT_IOT_GATT

BLE_ADVERTISEMENT_WAIT_SECONDS = 45
BLE_SESSION_KEEPALIVE_INTERVAL_SEC = 120
STATE_POLL_INTERVAL_SEC = 45

OPT_BLE_KEEPALIVE_SEC = "ble_keepalive_seconds"
OPT_STATE_POLL_SEC = "state_poll_seconds"
OPT_IOT_GATT_BACKEND = "iot_gatt_backend"
OPT_ESPHOME_DEVICE = "esphome_device_id"

IOT_GATT_BACKEND_AUTO = "auto"
IOT_GATT_BACKEND_BLUEZ = "bluez"
IOT_GATT_BACKEND_ESPHOME = "esphome"
DEFAULT_IOT_GATT_BACKEND = IOT_GATT_BACKEND_AUTO

POWER_CONFIRM_ATTEMPTS = 5
POWER_CONFIRM_DELAY_SEC = 0.55
POWER_CONFIRM_INITIAL_DELAY_SEC = 0.45

DATA_BLE_SESSION = "ble_session"
DATA_COORDINATOR = "coordinator"
DATA_KEEPALIVE_TASK = "keepalive_task"
