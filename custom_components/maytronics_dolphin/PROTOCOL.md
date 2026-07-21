# MyDolphin BLE protocol (legacy FFF0)

Verified against **MyDolphin Android 2.3.19** (`com.maytronics.mydolphin`, `classes2.dex` / androguard).

## GATT

| Role | UUID | Notes |
|------|------|--------|
| Service | `0000fff0-0000-1000-8000-00805f9b34fb` | All custom chars |
| Commands (FFF8) | `0000fff8-…` | `BTCommand` / `BLEManager.writePacket` |
| Config write (FFF9) | `0000fff9-…` | `ConfigParamsWrite` |
| Config read (FFFA) | `0000fffa-…` | `ConfigParamsRead` (3-byte request → 47-byte ACK) |
| Get status (FFFC) | `0000fffc-…` | Status notify/read |
| Internal (FFFD) | `0000fffd-…` | Internal params |

Advertisements typically include service `FFF0`. Many modules also advertise Texas Instruments manufacturer ID `0x000D`. Local name may be hex identity digits that differ from the on-air BD_ADDR.

**HA discovery filter (v1.17.1+):** `FFF0` alone is too broad (other TI boards use it). Auto-discovery requires FFF0 **plus** TI `0x000D` manufacturer data **and/or** a 12-hex local name. Unique ID prefers that hex name so one robot is not listed twice.

## Frame format

- **SOP** `0xAB`, CRC polynomial **`0xD8`** (`DolphinData.crcCalculation` / `updateCRC`).
- **19-byte `BTCommand`**: `[SOP, cmd, payload…]` with CRC in byte 18 over bytes 0–17. Used for power / RC / ping on **FFF8**.
- **3-byte short frame**: `[SOP, cmd, crc]` over first two bytes. Used for **ConfigParamsRead** requests on **FFFA**.

## Power (APK-verified)

`BLEManager.turnOnRobot` / `turnOffRobot` build a `BTCommand` and write to FFF8:

| APK enum | Wire byte | HA |
|----------|-----------|-----|
| `Startup_dolphin` | **7** | `BTCommandType.STARTUP` |
| `Shutdown_dolphin` | **6** | `BTCommandType.SHUTDOWN` |

## Status (APK-verified)

| APK `ConfigParamsRead.CommandType` | Wire | HA use |
|------------------------------------|------|--------|
| `PS_State` | **13** | Power / cleaner state |
| `Working_Clean_Mode` | **5** | Clean program sensor |
| `Cycle_Time` | **1** | Cycle length (ACK byte × **6** = minutes) |

### Cycle time write (APK-verified)

`BLEManager.setCicleTime(minutes)` builds `ConfigParamsWrite(cycle_time)` on **FFF9**:

- Divides minutes by **6**, packs the low byte of that unit into `mArgs[0]`, writes `0xFF` terminator, CRC on 46-byte frame.
- Common UI values: **60** (1 h, typically floor) and **120** (2 h, floor + wall).
- HA entity: **Cycle time** select (`1 hour` / `2 hours`). Manual **Power** uses this duration for display-only countdown (PS stops itself; HA does not SHUTDOWN for that timer).

`PS_State` ACK values: `0=OFF`, `1=ON`, `2=HOLD`, `3=PROGRAMMING`, `4=BIST`.

## Serial number

The app prompts for a **robot serial** (`DialogFactory.createSerialInputDialog`, strings like “Please enter the Serial number of the robot.”).

| Finding | Detail |
|---------|--------|
| **Not a BLE gate** | `turnOnRobot` / `turnOffRobot` / `writePacket` do **not** check serial before sending FFF8 commands. |
| Cloud / Parse | `FeaturesValidation.isSerialMU` looks up `MotorUnits` on Parse by `MUSerial` prefix — registration / product metadata. |
| BLE read path | `ConfigParamsRead.CommandType.Read_COM_board_serial_number` exists for reading COM-board serial over FFFA; HA does not require it for control. |

**Integration policy:** serial is optional diagnostics / device identity only. It must not block STARTUP/SHUTDOWN.

## Schedule

MyDolphin’s in-app schedule is separate from this wire protocol. Home Assistant’s schedule is a local timed STARTUP → duration → SHUTDOWN that must follow live `PS_State` (abort if power never confirms or robot stops early).

## Assumed / not re-verified every release

- Full joystick / LED / card-test payload branches (mirrored from earlier JADX of `BTCommand.getBytes()`).
- Exact advertising intervals and bonding behavior (device-dependent).
