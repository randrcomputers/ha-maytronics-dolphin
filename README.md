# Maytronics Dolphin (BLE) — Home Assistant (HACS)

Unofficial integration for **Maytronics Dolphin** robots that use the **MyDolphin** BLE protocol (reverse‑engineered from the Android app and HCI captures). **Not affiliated with Maytronics.** Use at your own risk.

## Requirements

- Home Assistant **2024.1+** (HAOS / Supervised supported).
- **Bluetooth** integration (built‑in adapter or **Bluetooth proxy** in range of the pool).
- Robot MAC address (from HA Bluetooth device list, nRF Connect, or router).

## Install (HACS)

1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add this GitHub repo, category **Integration**
3. Install **Maytronics Dolphin (BLE)**, restart HA
4. **Settings → Devices & services → Add integration → Maytronics Dolphin (BLE)**
5. Enter **MAC** and optional **name**

## Entities (v0.2)

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
