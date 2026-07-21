# Maytronics Dolphin (BLE) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Unofficial integration for **Maytronics Dolphin** robots that use the **MyDolphin** app (GATT service **`FFF0`**). Local Bluetooth control — no cloud account required.

**Not** MyDolphin **Plus** (v3.x / IoT). For Plus robots use **[ha-maytronics-dolphin-plus](https://github.com/randrcomputers/ha-maytronics-dolphin-plus)**.

Version **1.17.3** · Wire protocol notes: [`custom_components/maytronics_dolphin/PROTOCOL.md`](custom_components/maytronics_dolphin/PROTOCOL.md)

---

## Requirements

| Requirement | Notes |
|-------------|--------|
| Home Assistant **2024.1+** | HAOS, Supervised, Container, or Core |
| **Bluetooth** | Built-in adapter or [Bluetooth proxy](https://www.home-assistant.io/integrations/bluetooth/) in range of the pool |
| Robot BLE address | From HA **Settings → Bluetooth** (see **MAC / identity** below) |
| MyDolphin phone app | **Close it** while HA is connected — only one BLE client at a time |

---

## Install (HACS)

1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add: `https://github.com/randrcomputers/ha-maytronics-dolphin` — category **Integration**
3. Download **Maytronics Dolphin (BLE)** → restart Home Assistant
4. **Settings → Devices & services → Add integration → Maytronics Dolphin (BLE)**
5. Pick a discovered device, or enter the MAC manually

### Manual install

Copy `custom_components/maytronics_dolphin` into your HA `config/custom_components/` folder and restart.

---

## Setup & discovery (v1.17+)

- **Auto-discovery** and the setup picker list devices that advertise **`FFF0`** and look like a Dolphin: Texas Instruments manufacturer data **`0x000D`** and/or a **12-hex local name** (e.g. `22554C074D50`).
- Plain `FFF0` boards (e.g. named `sps`) are **ignored** so Discovered does not fill with junk.
- Manual MAC entry always remains available.

### MAC vs identity (important)

These PSUs often show **two** identifiers:

| Kind | Example | Use |
|------|---------|-----|
| **On-air BD_ADDR** | `E0:FF:F1:41:12:61` | What HA Bluetooth lists for **connect** — prefer this |
| **Stable identity** | `22:55:4C:07:4D:50` or name `22554C074D50` | Often printed / shown on the PS or in older docs |

If controls fail with *“did not advertise within 25s”*, open **Settings → Bluetooth** and configure the address HA actually sees (often `E0:FF:…`), not only the identity MAC.

The integration can also resolve a configured identity MAC to the on-air address when the advertisement’s **name** matches the same 12 hex digits and **FFF0** is present.

---

## What you get

| Entity / feature | Purpose |
|------------------|---------|
| **Power** | STARTUP / SHUTDOWN (`BTCommand` on `FFF8`) |
| **Cycle time** | PS cycle length: **1 hour** (floor) or **2 hours** (floor + wall) — APK `setCicleTime` |
| **Autoclean** | Autoclean enable/disable |
| **Cleaner state** | `PS_State` (off / on / hold / …) |
| **Clean program**, surface, working status | From config/status polls |
| **Cleaner schedule** | Built-in HA schedule (see below) |
| Buttons | Ping, Home, reset faults, RC quit, LED/card tests, … |
| Joystick numbers + send | Manual drive aids |
| **Release Bluetooth** | Drop the GATT session (optional) |

Works with the **[Pool Cleaner Card](https://github.com/randrcomputers/ha-pool-cleaner-card)** (integration schedule, Dolphin v1.15+; v1.17+ schedule states recommended).

### Schedule sensor (v1.17+)

| State | Meaning |
|-------|---------|
| `off` | Schedule disabled |
| `scheduled` | Armed; no timed run in progress |
| `active` | Timed run or manual Power cycle countdown in progress |

Attributes include day/time fields, `enabled`, `run_active`, `run_started_at`, `run_ends_at`, and `run_duration_minutes`. Manual Power uses the PS **Cycle time** for the countdown (display only — the PS stops itself). Timed runs abort on Power off or unexpected `PS_State` OFF, and do not stay “active” if the PS never powers on.

---

## Options

**Settings → Devices & services → Maytronics Dolphin (BLE) → Configure**

| Option | Typical use |
|--------|-------------|
| State poll interval | How often `PS_State` is read (`0` = commands only) |
| Periodic BLE release | Safety disconnect if a session is held |
| Responsive mode | Faster adaptive polling |
| Release Bluetooth button / diagnostic probe | Optional UI / deeper GATT reads |

---

## Troubleshooting

1. Confirm the robot appears under **Settings → Bluetooth** when awake and in range.
2. **Close MyDolphin** on the phone.
3. Prefer a **Bluetooth proxy near the pool** if the HA host is far away.
4. Use the **on-air** address from the Bluetooth list (see MAC vs identity above).
5. Try **Release Bluetooth**, wait, then Ping / Power again.
6. Debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.maytronics_dolphin: debug
```

---

## Plus vs this integration

| | **This repo** (legacy) | **[ha-maytronics-dolphin-plus](https://github.com/randrcomputers/ha-maytronics-dolphin-plus)** |
|---|---|---|
| App | MyDolphin **2.x** | MyDolphin **Plus** 3.x |
| BLE | GATT `FFF0` / `FFF8` | IoT GATT / Nordic UART |
| Typical hardware | Older BLE-only PSUs | IoT230 / E35i / Triton PS Plus class |

Install only the one that matches your app.

---

## Legal

Maytronics®, Dolphin®, and MyDolphin® are trademarks of their respective owners. Independent community software — not endorsed by Maytronics.

---

## Links

- **Issues:** [github.com/randrcomputers/ha-maytronics-dolphin/issues](https://github.com/randrcomputers/ha-maytronics-dolphin/issues)
- **Protocol:** [PROTOCOL.md](custom_components/maytronics_dolphin/PROTOCOL.md)
- **Pool Cleaner Card:** [ha-pool-cleaner-card](https://github.com/randrcomputers/ha-pool-cleaner-card)
- **Plus integration:** [ha-maytronics-dolphin-plus](https://github.com/randrcomputers/ha-maytronics-dolphin-plus)
