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
4. Use the **Address** in the device **tooltip** or Bluetooth device list, **not** the short **map label**. BLE often shows a **name** like `22554C074D50` (MAC digits without colons) while the **real connectable address** is different (e.g. `e0:ff:f1:41:12:61`). Put that **tooltip address** in the integration or HA will look up the wrong device. **v0.3.4+** normalizes MAC the same way as HA (lowercase); older builds uppercased the MAC and failed to find the device even when the Bluetooth map showed it.

## Install (HACS)

1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add this GitHub repo, category **Integration**
3. Install **Maytronics Dolphin (BLE)**, restart HA
4. **Settings → Devices & services → Add integration → Maytronics Dolphin (BLE)**
5. Enter **MAC** and optional **name**.

## Entities (v0.3.2)

| Type | What it does |
|------|----------------|
| **Switch — Power** | 3‑byte **Startup** (`AB0790`) / **Shutdown** (`AB0648`) |
| **Switch — Autoclean** | 19‑byte `Autoclean_Enable` ON/OFF |
| **Button — Quit RC mode** | 3‑byte `Quite_RC_mode` |
| **Button — Reset faults / Home / Reset dolphin / Reset filter / Ping** | Matching `BTCommand` short frames |
| **Button — Wall sensor poll** | Same as app’s periodic `Wall_Sensor` poll (chatty) |
| **Button — LED test** | `Leds` with value `0x01` (19‑byte) |
| **Number — Joystick X / Y** | −128…127; stored for send |
| **Button — Send joystick** | 19‑byte `Joystick_cmd` using X/Y (faster post‑delay, like app joystick path) |
| **Select — Card test type** | VDD…Servo calib (bytes 1–7) + **Run card test** button |

## Not implemented yet (needs more decompile / testing)

- **ConfigParamsRead / Write** (`fff9` / `fffa`) — cycle time, clean mode, weekly timer, RTC, features, etc.
- **GetStatusRead** (`fffc`) / **InternalParamsRead** (`fffd`) — status sensors.
- **Firmware / OTA** (`fffb`) — intentionally omitted (dangerous).

UUID mapping for `fff9`–`fffd` follows the order embedded in the MyDolphin dex string pool; if a feature hits the wrong characteristic on your model, adjust `const.py` and open a PR.

## Publishing to GitHub

See **`PUBLISHING.md`** in this folder for `git` + `gh` steps (you must be logged in: `gh auth login`).

## Legal

Maytronics and MyDolphin are trademarks of their owners. This project is independent community software.
