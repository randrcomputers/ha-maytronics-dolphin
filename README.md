# Maytronics Dolphin Plus (BLE) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Community integration for **Maytronics Dolphin** robots paired with the **MyDolphin Plus** app (v3.x). Control power and read status locally over Bluetooth — no cloud account required for BLE control.

> **Not the right integration?** Robots using the older **MyDolphin** app (GATT service `FFF0`) should use the legacy component in this monorepo: [`custom_components/maytronics_dolphin`](custom_components/maytronics_dolphin) (see its [README](custom_components/maytronics_dolphin/README.md)). The two integrations are separate; install only the one that matches your app.

> **Legacy changelog (1.17.0):** BLE auto-discovery + device picker; schedule sensor values `active` / `scheduled` / `off`; timed runs abort on manual Power off or unexpected `PS_State` OFF and require confirmed power after STARTUP. Protocol notes: [PROTOCOL.md](custom_components/maytronics_dolphin/PROTOCOL.md).


---

## What you get (v0.1.0)

| Feature | Status |
|---------|--------|
| **Power on/off** | `start_up_dolphin` / `shutdown_dolphin` (IoT GATT or Nordic UART, auto-detected) |
| **Status poll** | `system_status` → SM state, MU state, cleaning mode |
| **Short BLE sessions** | Connect per command/poll, then disconnect (same pattern as the legacy integration) |
| Schedule, autoclean, joystick, Pool Cleaner Card | Not yet — BLE MVP |

---

## Requirements

| Requirement | Notes |
|-------------|--------|
| **Home Assistant 2024.1+** | HAOS, Supervised, Container, or Core |
| **Bluetooth** | See **Bluetooth & proxies** below — IoT PSU models need a **local BlueZ adapter on the HA host** |
| **Robot BLE MAC** | From **Settings → Devices & services → Bluetooth**, or nRF Connect |
| **MyDolphin Plus app** | Close the app on your phone while HA is controlling the robot |
| **Robot class** | **IoT / PS Plus** profile (default). POP/buoy profiles are experimental |

---

## Install (HACS)

1. Install [HACS](https://hacs.xyz/) if needed.
2. HACS → **Integrations** → **⋮** → **Custom repositories**
3. Add: `https://github.com/randrcomputers/ha-maytronics-dolphin-plus` — category **Integration**
4. Download → restart Home Assistant
5. **Settings → Devices & services → Add integration → Maytronics Dolphin Plus (BLE)**
6. Enter the **Bluetooth MAC** and optional name.

### Manual install

Copy `custom_components/maytronics_dolphin_plus` into your HA `config/custom_components/` folder and restart.

---

## Setup options

During setup:

| Field | Default | When to change |
|-------|---------|----------------|
| **Protocol profile** | IoT / PS Plus | POP cordless or buoy models (experimental) |
| **BLE transport** | Auto-detect (recommended) | **IoT GATT** for E35i / IoT230 PS; **Nordic UART** for some Liberty-class units |

**Settings → Configure** (after install):

| Option | Default | Description |
|--------|---------|-------------|
| **State poll interval** | 45 s | How often `system_status` is read. `0` = commands only. |
| **Periodic BLE release** | 120 s | Safety disconnect if a session is still held. `0` = off. |
| **IoT command backend** | Auto | BlueZ dongle, ESPHome proxy, or auto-fallback |
| **ESPHome proxy device** | — | Required for ESPHome backend; flash `esphome/dolphin-plus-ble-proxy.yaml.example` first |

---

## Entities

| Entity | Type | Purpose |
|--------|------|---------|
| **Power** | Switch | Turn robot on / off |
| **SM state** | Sensor | Raw state machine byte (`0` ≈ off) |
| **MU state** | Sensor | Motor unit state byte |
| **Cleaning mode** | Sensor | Mode byte from status packet |

Power display follows `sm_state` when polls succeed; the switch may show **assumed** state briefly after a tap until the next poll confirms.

---

## How this differs from the legacy integration

| | **This repo** (Plus) | **[ha-maytronics-dolphin](https://github.com/randrcomputers/ha-maytronics-dolphin)** (legacy) |
|---|---|---|
| App | MyDolphin **Plus** 3.x | MyDolphin 2.x |
| BLE transport | Nordic UART / Plus IoT frames | GATT `FFF0` / `FFF8` |
| Protocol | Plus IoT SDK (`0xAB` frames) | 19-byte `BTCommand` |
| Typical robots | Triton PS Plus, Wi-Fi/IoT generation | Older BLE-only Dolphins |

You do **not** need both integrations unless you own two different robots.

---

## Bluetooth & proxies (v0.1.9+)

IoT PSU robots need commands sent via a **mirrored GATT server** (`fd5abba0` / `fd5abba1` notify), not a normal client write. Payloads are ASCII envelopes (`03:<hex>`), matching the Plus app / proven ESPHome implementations.

| Backend | When to use | Setup |
|---------|-------------|--------|
| **Auto** (default) | Try dongle first, fall back to ESPHome | Configure ESPHome proxy if you use proxies |
| **Local BlueZ** | USB or built-in Bluetooth on the HA host | None — works on HA OS with a pool-range dongle |
| **ESPHome proxy** | Bluetooth proxy only (no HA dongle) | Flash [`esphome/dolphin-plus-ble-proxy.yaml.example`](esphome/dolphin-plus-ble-proxy.yaml.example) on your pool ESP32 |

**Proxy setup (summary):**

1. Add `esp32_ble_server` + `dolphin_iot_notify` API action to your pool ESP32 (use the example YAML).
2. Keep `bluetooth_proxy: active: true` on the same device.
3. In HA: **Dolphin Plus → Configure → IoT command backend → ESPHome proxy GATT server** and select the ESPHome device.

| Setup | IoT PSU (E35i / IoT230) | Nordic UART (`6e400001`) |
|-------|-------------------------|---------------------------|
| HA dongle in range of PSU | Supported (BlueZ backend) | Supported |
| ESPHome proxy with dolphin-plus firmware | Supported (ESPHome backend) | Usually fine via proxy |
| Stock proxy only, no dolphin-plus firmware | Not supported | May work |

---

## Bluetooth tips

1. Confirm the robot appears under **Settings → Bluetooth** when awake and in range.
2. **Close MyDolphin Plus** on your phone — only one BLE client at a time.
3. For **IoT PSU** with a proxy: flash the [dolphin-plus GATT add-on](esphome/dolphin-plus-gatt-addon.yaml) — **SCREEK BP2-POE:** see [screek-bp2-poe-dolphin-plus.README.md](esphome/screek-bp2-poe-dolphin-plus.README.md) — then select the ESP in integration options.
4. For **IoT PSU** with a dongle: use **Auto** or **Local BlueZ**; the adapter must be in range of the PSU.
5. For **Nordic UART** robots, a standard [Bluetooth proxy](https://www.home-assistant.io/integrations/bluetooth/) is fine.
6. If power works but status stays unknown, open an issue with debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.maytronics_dolphin_plus: debug
```

---

## Supported hardware

Protocol derived from **MyDolphin Plus Android 3.4** (`com.maytronics.app`). Tested framing matches shipped `ble_iot_protocol.json`. Real-world confirmation on specific models is welcome via [issues](https://github.com/randrcomputers/ha-maytronics-dolphin-plus/issues).

**WiFi / cloud control** is out of scope for this integration (Plus app uses AWS IoT for Wi-Fi path). For cloud Wi-Fi robots see community projects such as [dolphin-robot](https://github.com/sh00t2kill/dolphin-robot) / `mydolphin_plus`.

---

## Legal

Maytronics®, Dolphin®, and MyDolphin® are trademarks of their respective owners. Independent community software — not endorsed by Maytronics.

---

## Links

- **Issues:** [github.com/randrcomputers/ha-maytronics-dolphin-plus/issues](https://github.com/randrcomputers/ha-maytronics-dolphin-plus/issues)
- **Legacy BLE integration:** [ha-maytronics-dolphin](https://github.com/randrcomputers/ha-maytronics-dolphin)
