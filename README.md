# Maytronics Dolphin (BLE) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Community integration for **Maytronics Dolphin** pool robots that speak the **MyDolphin** Bluetooth protocol. Control power, read cleaner status, and use optional advanced commands — all locally over BLE.


---

## What you get

- **Power on/off** from Home Assistant (same commands as the MyDolphin app)
- **Cleaner state** sensor (`off`, `on`, `hold`, `programming`, `self_test`)
- **Cleaning active** and diagnostic **PS state data OK** binary sensors
- **Autoclean** switch and extra **buttons** (home, reset faults, joystick, and more)
- **Built-in daily schedule** (v1.14.0+) — one or two start times per day, optional **Pool Cleaner Card** UI (no YAML helpers)
- **Short BLE sessions** — connect only for each command or status poll, then disconnect (reduces “stuck Bluetooth light / frozen robot” reports)
- Works with the optional **[Pool Cleaner Card](https://github.com/randrcomputers/ha-pool-cleaner-card)** Lovelace frontend



---

## Requirements

| Requirement | Notes |
|-------------|--------|
| **Home Assistant 2024.1+** | HAOS, Supervised, Container, Core |
| **Bluetooth** | Built-in adapter **or** [Bluetooth proxy](https://www.home-assistant.io/integrations/bluetooth/) (ESPHome, Shelly, etc.) **near the pool** |
| **Robot MAC address** | From **Settings → Devices & services → Bluetooth**, or nRF Connect |
| **One BLE client at a time** | Close **MyDolphin** on your phone while testing HA |

---

## Install (HACS)

1. Install [HACS](https://hacs.xyz/) if you have not already.
2. HACS → **Integrations** → **⋮** → **Custom repositories**
3. Add repository: `https://github.com/randrcomputers/ha-maytronics-dolphin`  
   Category: **Integration**
4. Open the new repo → **Download** → restart Home Assistant
5. **Settings → Devices & services → Add integration → Maytronics Dolphin (BLE)**
6. Enter the robot **Bluetooth MAC** (format `AA:BB:CC:DD:EE:FF`) and an optional friendly name.

This integration is **not** in the default HACS store; the custom repository URL above is how everyone installs it today.

---

## Pool Cleaner Card (optional)

For a dashboard card with robot/PSU artwork, status pill, power button, and **schedule panel**:

1. Install **[Pool Cleaner Card](https://github.com/randrcomputers/ha-pool-cleaner-card)** (HACS → **Frontend** → custom repo) — use a build that supports integration schedule (integration **v1.14.0+**).
2. Add card → **Pool Cleaner Card**.
3. Choose your **Dolphin device** — entities auto-fill.
4. Enable **Show schedule panel**. Leave **Schedule backend** on **Auto** (uses integration schedule; no YAML package).

| Card field | Integration entity |
|------------|-------------------|
| Power switch | **Power** |
| Cleaner state | **Cleaner state** |
| Cleaning active | **Cleaning active** (optional) |
| BLE OK / connected | **Leave blank** (recommended) or **PS state data OK** (see below) |
| Schedule | **Auto** + Dolphin device (v1.14.0+) — no helper mapping |

**Tip:** Leave **BLE OK / connected** empty. The card then treats “reachable” as the power entity not being `unavailable`. Mapping **PS state data OK** makes the corner icon mean “last status poll succeeded,” which often goes dark while the robot is still fine.

---

## Entities

All entities are created on one **device** per configured robot.

### Everyday use

| Entity | Type | Purpose |
|--------|------|---------|
| **Power** | Switch | Turn robot on (**Startup**) / off (**Shutdown**) via GATT `fff8` |
| **Cleaner state** | Sensor | Text status from **PS_State** poll |
| **Clean program** | Sensor | Selected mode from **Working_Clean_Mode** (`regular`, `ultraclean`, `floor_only`*, `waterline`, …) |
| **Cleaning surface** | Sensor | Best-effort **floor** / **wall** / **waterline** while running (see below) |
| **Working status** | Sensor | Stabilized `at_work` / `finished` / `fault` (v0.7.6+ holds last good value through brief read gaps; see attributes `working_status_raw`, `working_status_held`) |
| **Cleaning active** | Binary sensor | On when state is anything except `off` |
| **Cleaner schedule** | Sensor | Stored schedule state (`on`/`off`) + attributes for card (v1.14.0+) |
| **Autoclean** | Switch | Enable/disable autoclean command (not synced from robot state) |

### Diagnostics

| Entity | Type | Purpose |
|--------|------|---------|
| **PS state data OK** | Binary sensor | On when the last poll returned a parseable **PS_State** |
| **Status raw (fffc)** | Sensor | Optional hex read (may be empty on some models) |
| **Status raw (fffd)** | Sensor | Optional hex read (may be empty on some models) |

### Advanced (buttons & helpers)

Quit RC mode, Reset faults, Home, Reset dolphin, Reset filter indication, Ping, Wall sensor poll, LED test, Joystick X/Y + Send joystick, Card test type + Run card test.

When enabled in options: **Release Bluetooth** — forces disconnect if HA still holds the link.

### Built-in cleaner schedule (v1.14.0+)

Optional **daily schedule** stored inside the integration (no YAML helpers or automations). Used automatically by the **Pool Cleaner Card** when a **Dolphin device** is selected and **Schedule backend** is **Auto**.

| Feature | Detail |
| --- | --- |
| **Run 1** | Start time + 1 h or 2 h + **own weekdays** when master schedule is **on** |
| **Run 2** | Optional second daily time + duration + **own weekdays** (own on/off on the card) |
| **Days** | Per run: `run1_days` and `run2_days` as `0`–`6` (Mon–Sun). Legacy `days` in storage migrates to both. |
| **Persistence** | Saved in `.storage/maytronics_dolphin.schedule.<entry_id>` — survives HA restart |
| **Time changes** | Apply immediately — no automation reload (minute tick reads stored times) |
| **Repeats** | Each enabled run fires **once per day** on selected days while HA is running |

**Sensor:** `sensor.<name>_cleaner_schedule` — state `on`/`off`; attributes:

| Attribute | Meaning |
| --- | --- |
| `run1_days` | e.g. `0,1,2,3,4,5,6` |
| `run2_days` | e.g. `0,6` (weekends only, etc.) |
| `run1_time` | `HH:MM` (24h) |
| `run1_duration_minutes` | `60` or `120` |
| `run2_enabled` | `true` / `false` |
| `run2_time` | `HH:MM` |
| `run2_duration_minutes` | `60` or `120` |

**Services** (Developer tools → Actions):

| Service | Purpose |
| --- | --- |
| `maytronics_dolphin.set_schedule` | Update any schedule fields (`device_id` required) |
| `maytronics_dolphin.run_timed` | Power on → wait → off (`duration_minutes`: 60 or 120) |

Example `set_schedule` data:

```yaml
device_id: YOUR_DEVICE_ID
enabled: true
run1_days: "0,1,2,3,4,5,6"
run1_time: "08:09"
run1_duration_minutes: 120
run2_enabled: true
run2_days: "0,6"
run2_time: "17:00"
run2_duration_minutes: 60
```

**Migration:** If you already use the Pool Cleaner Card **YAML package** ([`pool-cleaner-schedule.yaml`](https://github.com/randrcomputers/ha-pool-cleaner-card/blob/main/examples/pool-cleaner-schedule.yaml)), **disable those automations** or set the card **Schedule backend** to **helpers** — otherwise **both** schedulers may run. New setups should use **integration schedule only**.

---

## How status and power work

Understanding this avoids “wrong” dashboard readings:

1. **Power switch**  
   Sends a 19-byte command immediately. Display follows **PS_State** when a poll succeeds; otherwise Home Assistant may show **assumed** on/off from your last tap.

2. **Cleaner state**  
   Updates only after a successful **PS_State** read (about every poll interval). Can show `unknown` between polls or after a failed read.

3. **PS state data OK**  
   Means “the status **read** worked,” not “Bluetooth is connected like the phone app.” It can be **off** while **Power** commands still work.

4. **Cleaning active**  
   On for `hold`, `programming`, and `self_test` as well as `on` — not only “actively cleaning the pool.”

5. **Clean program**  
   The **program you selected** in the app (e.g. `regular`, `ultraclean`, `waterline`) — **not** the same as live surface position.

6. **Cleaning surface** (v0.7.2+)  
   While the robot is **on** (PS_State not `off`), the integration also reads **InternalParamsRead** (`fffd`, 132-byte block) and infers surface:

   | Value | Meaning |
   |-------|---------|
   | `floor` | Floor-only program (APK marker: climb byte **234** + clean byte **1**) or regular/fast-style programs |
   | `waterline` | Waterline program |
   | `wall` | **Experimental** — ultraclean + internal **phase byte** = 1 (offset 30 in APK layout; confirm on your unit via entity attributes) |
   | `unknown` | Ultraclean or other modes where live surface is not decoded yet |
   | `unavailable` | Robot off / no internal read |

   The MyDolphin app does **not** expose a dedicated “on wall now” label in BLE; wall/floor appears mainly as **fault** text (“Wall/floor sensor”). If **Cleaning surface** stays `unknown` during ultraclean, check attributes **`phase_byte`** / **`motor_aux_byte`** in Developer tools and open an issue with those values from floor vs wall.

\* In the APK, `floor_only` shares wire code **1** with `regular`; **Cleaning surface** uses the internal **234** marker to detect floor-only anyway.

**Card shows “Unknown”** → **Cleaner state** is `unknown` (HA lost a good status read). That does **not** always mean the robot is locked up. Check the physical unit: still running? BT LED stuck on? Responds to **Power**?

---

## Integration options

**Settings → Devices & services → Maytronics Dolphin (BLE) → Configure**

| Option | Default | Description |
|--------|---------|-------------|
| **State poll interval (PS_State)** | `45` s | How often HA reads status. Use `60`–`120` if the robot ever wedges; `0` = no automatic polls (commands only). |
| **Periodic BLE release** | `120` s | Disconnect if still connected (safety net). `0` = off. Ignored when persistent session is on. |
| **Persistent BLE session** | Off | **Experimental:** keep GATT connected between polls/commands (faster toggles; may wedge robot — use **Release Bluetooth** if BT LED sticks on). |
| **Responsive mode** | Off | Faster adaptive **PS_State** polling when robot looks active (does **not** keep BLE connected — use **Persistent BLE session** for that) |
| **Show Release Bluetooth button** | On | Adds **Release Bluetooth** on the device |
| **Diagnostic fffc/fffd reads during poll** | Off | Extra GATT reads each poll — leave off unless debugging |

By default HA does **not** keep a permanent Bluetooth connection (connect → act → disconnect each time). Enable **Persistent BLE session** only if you want to test an always-on link.

---

## Bluetooth tips

### Robot not found

1. **Settings → Devices & services → Bluetooth** — confirm the Dolphin appears when the robot is awake and in range.
2. **Close MyDolphin** on the phone; another client can block or delay GATT.
3. Put a **Bluetooth proxy** in the pool area (ESPHome `bluetooth_proxy` is a common choice).
4. After HA restarts, the first action may wait up to **25 seconds** for a connectable advertisement.

### MAC address confusion

BLE listings sometimes show a **name** like `22554C074D50` (MAC digits without colons) while the **connectable address** differs (e.g. `e0:ff:f1:41:12:61`). Use the address from the Bluetooth device details or tooltip. The integration can resolve some name/MAC mismatches when the MyDolphin **FFF0** service is visible.

### If the robot “freezes” (BT LED stuck on)

1. Tap **Release Bluetooth** (if shown) or reload the integration.
2. **Power-cycle** the robot (dock/unplug) once.
3. Increase **State poll** to **60–120 s** or set **0** temporarily.
4. Keep **Diagnostic fffc/fffd** disabled unless you are capturing logs.
5. Do not run **MyDolphin** and HA control at the same time during testing.

### Debug logging

**Settings → System → Logs** → enable debug for:

```yaml
logger:
  default: info
  logs:
    custom_components.maytronics_dolphin: debug
```

---

## Setup notes

- **Manual setup only** — enter the MAC in the config flow. Automatic Bluetooth discovery is disabled to avoid pairing random FFF0 devices.
- If you previously added wrong devices from an older discovery build, remove them under **Devices & services** and keep only your real Dolphin.

---

## Supported hardware

Built and tested against **MyDolphin Android app 2.3.19** packet layouts (power on `fff8`, **PS_State** command `13` on `fffa` / `fff9`). Many Dolphin models using service **FFF0** work; some characteristics may differ — open an issue with model name and logs.

**Firmware update / OTA** (`fffb`) is intentionally not exposed.

---

## Legal

Maytronics®, Dolphin®, and MyDolphin® are trademarks of their respective owners. This project is independent community software with no endorsement from Maytronics.

---

## Links

- **Issues:** [GitHub Issues](https://github.com/randrcomputers/ha-maytronics-dolphin/issues)
- **Pool Cleaner Card:** [ha-pool-cleaner-card](https://github.com/randrcomputers/ha-pool-cleaner-card)
