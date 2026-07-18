# Maytronics Dolphin (BLE) — legacy MyDolphin

Home Assistant custom component for robots that use the **MyDolphin** app (GATT service **FFF0**), not MyDolphin Plus.

Version **1.17.1** · Protocol notes: [PROTOCOL.md](PROTOCOL.md)

## Setup (v1.17+)

1. Ensure the robot appears under **Settings → Devices & services → Bluetooth**.
2. **Add integration → Maytronics Dolphin (BLE)**.
3. Pick a discovered Dolphin (FFF0 **and** TI manufacturer data and/or a 12-hex local name like `1C4A2B274D52`), or choose **Enter MAC address manually**.
4. HA auto-discovery uses the same filter — plain `FFF0` boards named e.g. `sps` are ignored (**v1.17.1+**).

Close the MyDolphin phone app while HA is connected (single BLE client).

## Schedule sensor (breaking change in 1.17)

`Cleaner schedule` native value is no longer simply `on`/`off` for “schedule enabled”:

| Value | Meaning |
|-------|---------|
| `off` | Schedule disabled |
| `scheduled` | Schedule armed; no timed run in progress |
| `active` | Timed run confirmed via `PS_State` ON |

Attributes still include `enabled`, day/time fields, plus `run_active` and `run_ends_at`.

Timed runs now:

- Require `PS_State` ON after STARTUP (unplugged PS will not look “active”).
- Abort when you turn **Power** off, or when `PS_State` reports OFF mid-run.
- Skip a fire if the last poll failed with no known state (likely unreachable).

## Serial number

The MyDolphin app asks for a robot serial for **cloud/Parse registration**. BLE STARTUP/SHUTDOWN are **not** gated by serial. See [PROTOCOL.md](PROTOCOL.md).
