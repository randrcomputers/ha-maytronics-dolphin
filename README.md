# Maytronics Dolphin (BLE) — Home Assistant (HACS)

Unofficial integration for **Maytronics Dolphin** robots that use the **MyDolphin** BLE protocol (reverse‑engineered from the Android app and HCI captures). **Not affiliated with Maytronics.** Use at your own risk.

## Requirements

- Home Assistant **2024.1+** (HAOS / Supervised supported).
- **Bluetooth** integration (built‑in adapter or **Bluetooth proxy** in range of the pool).
- Robot **Bluetooth MAC** (required) — from HA’s Bluetooth device list or nRF Connect.

## Bluetooth discovery (disabled in v0.3.2)

Automatic HACS/HA discovery via `manifest.json` **Bluetooth matchers** was **removed**:

- **v0.3.0** — matcher on service **FFF0** only matched **many** non‑Dolphin devices.
- **v0.3.1** — TI + FFF0 matcher fixed false positives, but some installs reported **HACS no longer listing the integration** (likely validation / refresh quirks with combined matchers).

**v0.3.2** ships **manual setup only** (MAC in the config flow) so HACS stays reliable. Discovery can be revisited later (e.g. separate flow or validated matcher).

### Clean up mistaken v0.3.0 entries

**Settings → Devices & services → Maytronics Dolphin (BLE)** — remove config entries / devices that are **not** your pool cleaner (each bogus entry added ~15 entities). Keep only the real Dolphin (e.g. MAC `22:55:4C:…`).

## Troubleshooting: "not visible to Home Assistant"

HA only connects if it has **recently heard** your robot on Bluetooth (it keeps a small cache of devices). **v0.3.3+** waits up to **25 seconds** on each command for a connectable advertisement if the MAC is not in the cache yet (for example right after a restart).

1. **Settings → Devices & services → Bluetooth** — scroll the list. If your Dolphin **never** appears, HA cannot connect until it does (range, walls, water).
2. **Close MyDolphin** on the phone and ensure the robot is **not** connected elsewhere — some units advertise rarely while another client holds GATT.
3. **Bluetooth proxy** (ESPHome, Shelly, etc.) **near the pool** often works better than the HA server in the house.
4. Use the **Address** in the device **tooltip** or Bluetooth device list, **not** the short **map label**. BLE often shows a **name** like `22554C074D50` (MAC digits without colons) while the **real connectable address** is different (e.g. `e0:ff:f1:41:12:61`). Put **either** value in the integration: **v0.3.5+** can resolve the on-air address when the config matches the advertised **name** (same 12 hex digits) **and** the MyDolphin **FFF0** service is present (prefers **Texas Instruments** manufacturer `0x000D` when several FFF0 devices exist). **v0.3.4** fixed lowercase MAC lookups for HA’s cache.

## Install (HACS)

1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add this GitHub repo, category **Integration**
3. Install **Maytronics Dolphin (BLE)**, restart HA
4. **Settings → Devices & services → Add integration → Maytronics Dolphin (BLE)**
5. Enter **MAC** and optional **name**.

## Entities (v0.5.0)

| Type | What it does |
|------|----------------|
| **Switch — Power** | 19-byte ``BTCommand`` **Startup_dolphin** / **Shutdown_dolphin** (``BLEManager.turnOnRobot`` / ``turnOffRobot`` on FFF8). **v0.5.0+** also polls **PS_State** via ``ConfigParamsRead`` on **fffa** every ~45s so HA updates when the robot is powered off **on the unit** (when BLE parse succeeds). |
| **Switch — Autoclean** | 19-byte ``Autoclean_Enable`` ON/OFF (``BLEManager.setAutocleanEnabled``) |
| **Button — Quit RC / faults / Home / …** | 19-byte ``BTCommand`` for each opcode (``writePacket`` style), not 3-byte short frames |
| **Button — Wall sensor poll** | 19-byte ``Wall_Sensor`` |
| **Button — LED test** | ``Leds`` + value ``0x01`` |
| **Number — Joystick X / Y** | −128…127; stored for send |
| **Button — Send joystick** | ``BLEManager.sendJoystickCommand`` path (shorter post-delay) |
| **Select — Card test type** | Card test sub-byte + **Run card test** (``BLEManager.runCardTest``) |

**Clean mode (“normal”, floor only, etc.)** in the app is ``BLEManager.setCleanMode`` → ``ConfigParamsWrite(CommandType.Working_Clean_Mode)`` on **fff9** (not an extra FFF8 opcode). Not implemented in this integration yet.

## Not implemented yet (needs more decompile / testing)

- **ConfigParamsWrite** (`fff9`) — cycle time, clean mode, weekly timer, RTC, features, etc.
- **ConfigParamsRead** beyond **PS_State** (same `fffa` path as the app’s read characteristic).
- **GetStatusRead** (`fffc`) / **InternalParamsRead** (`fffd`) — status sensors.
- **Firmware / OTA** (`fffb`) — intentionally omitted (dangerous).

**v0.5.0** aligns **read/write UUIDs with JADX** (`ConfigParamsRead` → `fffa`, `ConfigParamsWrite` → `fff9`), which differs from a naive dex string-pool ordering; if your build behaves differently, adjust `const.py` and open a PR.

## Publishing to GitHub

See **`PUBLISHING.md`** in this folder for `git` + `gh` steps (you must be logged in: `gh auth login`).

## Legal

Maytronics and MyDolphin are trademarks of their owners. This project is independent community software.
