# Maytronics Dolphin (BLE) — Home Assistant (HACS)

Unofficial integration for **Maytronics Dolphin** robots that use the **MyDolphin** BLE protocol (reverse‑engineered from the Android app and HCI captures). **Not affiliated with Maytronics.** Use at your own risk.

## Requirements

- Home Assistant **2024.1+** (HAOS / Supervised supported).
- **Bluetooth** integration (built‑in adapter or **Bluetooth proxy** in range of the pool).
- Robot MAC address — **optional** if you use **Bluetooth discovery** (v0.3+).

## Bluetooth discovery (v0.3+)

The integration declares a **strict** Bluetooth matcher:

- **Service UUID** `0000fff0-0000-1000-8000-00805f9b34fb` (MyDolphin `CC2540_SERVICE_UUID`)
- **Manufacturer ID** `13` (0x000D — **Texas Instruments**, the radio on Maytronics units in HCI captures)

**Why:** The 16‑bit UUID **0xFFF0** is used by many unrelated BLE products as a generic vendor slot. Matching **FFF0 alone** (v0.3.0) incorrectly offered **every** such device as a Dolphin — pool sensors, Shelly, etc. **v0.3.1** requires **TI + FFF0** together.

If your robot uses a **non‑TI** module and discovery never appears, use **manual** MAC setup and open an issue with nRF advertisement details.

### Clean up mistaken v0.3.0 entries

**Settings → Devices & services → Maytronics Dolphin (BLE)** — remove config entries / devices that are **not** your pool cleaner (each bogus entry added ~15 entities). Keep only the real Dolphin (e.g. MAC `22:55:4C:…`).

## Troubleshooting: "not visible to Home Assistant"

HA only connects if it has **recently heard** your robot on Bluetooth (it keeps a small cache of devices).

1. **Settings → Devices & services → Bluetooth** — scroll the list. If your Dolphin **never** appears, HA cannot connect until it does (range, walls, water).
2. **Close MyDolphin** on the phone and ensure the robot is **not** connected elsewhere — some units advertise rarely while another client holds GATT.
3. **Bluetooth proxy** (ESPHome, Shelly, etc.) **near the pool** often works better than the HA server in the house.
4. Confirm the MAC matches what that Bluetooth page shows (format `22:55:4C:07:4D:50`).

## Install (HACS)

1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add this GitHub repo, category **Integration**
3. Install **Maytronics Dolphin (BLE)**, restart HA
4. **Settings → Devices & services → Add integration → Maytronics Dolphin (BLE)**
5. Either accept a **discovered** Maytronics Dolphin entry when it appears, **or** choose **Manual** / **Add integration** again and enter **MAC** + optional **name**.

## Entities (v0.3)

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
