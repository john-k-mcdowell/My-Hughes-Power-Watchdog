# Hughes Power Watchdog BLE Protocol Documentation

This document describes the two Bluetooth Low Energy (BLE) protocols used by Hughes Power Watchdog devices.

- **V1 protocol** — Used by Gen 1 devices (Bluetooth only, model suffix EPO)
- **V2 protocol** — Used by Gen 2 devices (WiFi + Bluetooth, model suffix EPOW)

### Sources

V1 protocol details are drawn from three independent sources:

1. The original [ESPHome implementation](https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog) by spbrogan, tango2590, and makifoxgirl.
2. **Live Bluetooth HCI captures** and runtime testing against a real Gen 1 device (PWD50-EPD / PWD-VM-30A) during development of this integration.
3. Reverse engineering of the official `powerwatchdog2` Android application (ASCII command strings, ack responses, error record format).

V2 protocol details are drawn from:

1. Live Bluetooth HCI captures against real Gen 2 devices (PWD30EPOW / PWD50EPOW).
2. Reverse engineering of the `com.yw.watchdog` Android application source (`Cmd.java`, `Protocol.java`, `Package.java`, `DeviceManager.java`).
3. Cross-referenced against the [TechBlueprints/dbus-power-watchdog](https://github.com/TechBlueprints/dbus-power-watchdog) Venus OS implementation, which provides independent decoders (`power_watchdog_proto_gen1.py`, `power_watchdog_proto_gen2.py`) and per-generation specs (`PROTOCOL-GEN1.md`, `PROTOCOL-GEN2.md`). This reference clarified several fields previously listed as "unknown" here — see the notes below.

## Device Generations

| Generation | Connectivity | Model Suffix | BLE Device Name | Mobile App |
|-----------|-------------|-------------|----------------|-----------|
| **Gen 1** | Bluetooth only | EPO | `PMD*`, `PWS*`, `PMS*` | [Power Watchdog Bluetooth ONLY](https://play.google.com/store/apps/details?id=com.hughes.epo) |
| **Gen 2** | WiFi + Bluetooth | EPOW | `WD_V5_*`, `WD_E5_*`, `WD_V6_*`, `WD_E6_*` | [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) |

The V2 protocol header `$yw@` corresponds to the `com.yw.watchdog` package name of the official Gen 2 WiFi app. Device name prefixes like `WD_V5`, `WD_E5`, `WD_V6`, `WD_E6` are hardware BLE advertisement names and do not change — only our internal protocol label changed from "V5" to "V2".

## Protocol Overview

| Feature | Gen 1 V1 (PMD/PWS/PMS) | Gen 2 V2 (WD_V5/WD_E5/WD_V6/WD_E6) |
|---------|---------------------------|-------------------|
| Device Names | `PMD*`, `PWS*`, `PMS*` | `WD_V5_*`, `WD_E5_*`, `WD_V6_*`, `WD_E6_*` |
| Service UUID | `0000ffe0-0000-1000-8000-00805f9b34fb` | `000000ff-0000-1000-8000-00805f9b34fb` |
| TX Characteristic | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` |
| RX Characteristic | `0000fff5-0000-1000-8000-00805f9b34fb` | Same as TX (bidirectional) |
| Packet Header | `01 03 20` | `24 79 77 40` (`$yw@`) |
| Data Size | 40 bytes (2x20-byte chunks) | Variable (45 bytes single-block, 79 bytes dual-block) |
| Initialization | None (subscribe to notifications) | Send `!%!%,protocol,open,` |
| Line Support | Dual-line (50A models send separate packets) | Single-block (30A) or dual-block (50A) |
| Data Encoding | Big-endian int32 / 10000 (values always non-negative in practice; see note under V1 packet structure) | Big-endian unsigned int32 / 10000 |
| Commands | ASCII strings via RX characteristic | Binary `$yw@` framed packets via bidirectional characteristic |

## Protocol Detection

The integration uses a two-step detection approach:

1. **Name-based guess** (at startup): Checks device name prefix against known lists
2. **Service-based confirmation** (on first BLE connection): Probes the device's BLE service UUIDs to confirm the protocol

If the service detection disagrees with the name-based guess, the service result takes priority and a warning is logged.

## Error Codes (Both Protocols)

Error codes are shared across both protocols (from Hughes official documentation and app source):

| Code | ID | Description |
|------|----|-------------|
| 0 | - | No Error |
| 1 | E1 | Line 1 voltage exceeded 132V or dropped below 104V |
| 2 | E2 | Line 2 voltage exceeded 132V or dropped below 104V |
| 3 | E3 | Line 1 amperage rating exceeded |
| 4 | E4 | Line 2 amperage rating exceeded |
| 5 | E5 | Line 1 hot and neutral wires reversed |
| 6 | E6 | Line 2 hot and neutral wires reversed |
| 7 | E7 | Ground connection lost |
| 8 | E8 | No neutral circuit detected (50A models only) |
| 9 | E9 | Surge protection capacity depleted - replace surge board |
| 11 | F1 | Frequency error |
| 12 | F2 | Frequency error |

**Naming note:** Don't confuse error codes `E8`/`E9` with Hughes hardware model suffixes. Both exist:
- **Error codes `E8`/`E9`** are the numeric fault codes above.
- **Hardware models `E8`/`V8`/`E9`/`V9`** are the autoformer "booster" variants that can regulate output voltage. Non-booster model suffixes are `V5`/`E5`/`V6`/`E6`/`V7`/`E7`.

The booster vs non-booster distinction matters because several V2 data-packet fields (output voltage, temperature, boost mode) only carry meaningful values on booster hardware.

---

## Gen 1 V1 Protocol (PMD/PWS/PMS)

Used by Gen 1 Bluetooth-only devices (EPO models). Compiled from three sources:

1. Original [ESPHome implementation](https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog) by spbrogan, tango2590, and makifoxgirl — confirmed the TX characteristic, header, and core data fields (voltage, current, power, energy).
2. Live runtime testing of this integration against real Gen 1 hardware (PWD50-EPD and PWD-VM-30A) — confirmed the frequency field, the line-ID markers for 50A dual-line devices, and the two-chunk reassembly behavior.
3. Reverse engineering of the `powerwatchdog2` Android app — provided the ASCII command strings, ack responses, and 16-byte error record format.

The independent [TechBlueprints/dbus-power-watchdog](https://github.com/TechBlueprints/dbus-power-watchdog) implementation corroborates the same byte layout.

### GATT Profile

| Item | UUID |
|------|------|
| Service | `0000ffe0-0000-1000-8000-00805f9b34fb` |
| TX Characteristic (device sends data) | `0000ffe2-0000-1000-8000-00805f9b34fb` |
| RX Characteristic (device receives commands) | `0000fff5-0000-1000-8000-00805f9b34fb` |

### Connection Sequence

1. Connect to device via BLE
2. Subscribe to notifications on the TX characteristic (`0000ffe2-...`)
3. Device streams data packets continuously (~1 second intervals)
4. No initialization command needed

### Data Packet Structure (40 bytes)

The device sends 40 bytes in two 20-byte BLE notification chunks. The chunks are buffered and parsed together.

> **Signed vs unsigned:** This integration decodes V1 fields as big-endian *signed* int32 (following the ESPHome reference); TechBlueprints/dbus-power-watchdog decodes them as *unsigned*. Either is correct in practice — voltage, current, power, and energy are always non-negative, so the high bit is never set in normal operation.

#### Chunk 1 (bytes 0-19)

| Offset | Size | Field | Format | Status |
|--------|------|-------|--------|--------|
| 0-2 | 3 | Header | `01 03 20` (identifies data packets) | **Decoded** |
| 3-6 | 4 | Voltage | Big-endian signed int32 / 10000 (volts) | **Decoded** |
| 7-10 | 4 | Current | Big-endian signed int32 / 10000 (amps) | **Decoded** |
| 11-14 | 4 | Power | Big-endian signed int32 / 10000 (watts) | **Decoded** |
| 15-18 | 4 | Energy | Big-endian signed int32 / 10000 (kWh) | **Decoded** |
| 19 | 1 | Error Code | Unsigned byte (0=OK, 1=E1, etc.) | **Decoded** |

#### Chunk 2 (bytes 20-39)

| Offset | Size | Field | Format | Status |
|--------|------|-------|--------|--------|
| 20-30 | 11 | Unknown/Padding | Purpose not decoded | Unknown |
| 31-34 | 4 | Frequency | Big-endian signed int32 / 100 (Hz) | **Decoded** |
| 35-36 | 2 | Unknown/Padding | Purpose not decoded | Unknown |
| 37-39 | 3 | Line ID | `00 00 00` = Line 1, `01 01 01` = Line 2 | **Decoded** |

### Dual-Line Support

50A Gen 1 devices (e.g., PWD50-EPD) send separate data packets for each line. Each packet includes a Line ID (bytes 37-39) to identify which line the data belongs to:

- `00 00 00` = Line 1
- `01 01 01` = Line 2

30A devices send only Line 1 data.

### Error Record Packet (16 bytes)

Historical errors are transmitted in 16-byte chunks. Identified by ASCII `Er` at the beginning and `E` at the end.

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-1 | 2 | Header | `45 72` (ASCII `Er`) |
| 2 | 1 | serialNum | Error record index/ID |
| 3 | 1 | Separator | `3A` (ASCII `:`) |
| 4-8 | 5 | startTime | Year(+2000), Month, Day, Hour, Minute |
| 9-13 | 5 | endTime | Year(+2000), Month, Day, Hour, Minute. All `0x55` = ongoing |
| 14 | 1 | Trailer | `45` (ASCII `E`) |
| 15 | 1 | ErrorCode | Error code ID (1-9 for E1-E9, 11=F1, 12=F2) |

### V1 Commands (App -> Device) — **Work in Progress**

> **Status (as of v0.8.0-beta.8): V1 command support is not yet functional.** BLE writes are accepted by the device (the characteristic acknowledges the write at the GATT layer) but the Power Watchdog takes no action — no relay toggle, no energy reset, no ack string over the notification channel. The exact wire format used by the official `powerwatchdog2` app has not been captured yet and is still to be determined.
>
> During beta testing, the following combinations were all tried and all silently ignored by the device:
> - Characteristic `0xfff5` with write-without-response
> - Characteristic `0xfff5` with write-with-response
> - Characteristic `0x1003` (discovered via GATT enumeration) with write-with-response
> - Characteristic `0x1005` with write-with-response
> - ASCII payload with no terminator, and with `\r\n` terminator
>
> Until an HCI capture from the official Android app reveals the correct framing, **V1 command entities (relay switch, backlight light, energy-reset button, error-delete button) are hidden from Home Assistant on V1 devices.** The code paths remain in the codebase (`_send_v1_command` in `coordinator.py`) for future work.
>
> The [TechBlueprints/dbus-power-watchdog](https://github.com/TechBlueprints/dbus-power-watchdog) reference implementation also does not send any V1 commands — its Gen 1 handler is explicitly receive-only, noting "Gen1 streams telemetry without a handshake."

The ASCII command strings observed in the Android app (likely candidates once the wire format is understood):

| Command | Expected Ack String | Description |
|---------|-------------------|-------------|
| `relayOn` | `"relay on"` | Turn power relay on |
| `reset` | `"RESET"` | Reset accumulated kWh to 0 |
| `deleteIndexRecord` | `"del:rec"` | Delete specific error record |
| `deleteAllRecord` | `"del:recA"` | Delete all error history |
| `setTime` | `"set:t"` | Sync device clock to phone |
| `backLight` | `"set:blX"` | Set LED brightness (0-4) |
| `powerOnTime` | `"power on time:" + 5 bytes` | Request last power-on date/time |

The integration currently writes the bare ASCII string to characteristic `0x1003` with write-with-response; the device accepts the write but does not act on it.

### Decoding Example (Python)

```python
import struct

def decode_v1_packet(data: bytes) -> dict:
    """Decode a 40-byte Gen 1 V1 data packet."""
    if len(data) < 40 or data[0:3] != b'\x01\x03\x20':
        return None

    voltage = struct.unpack('>i', data[3:7])[0] / 10000
    current = struct.unpack('>i', data[7:11])[0] / 10000
    power = struct.unpack('>i', data[11:15])[0] / 10000
    energy = struct.unpack('>i', data[15:19])[0] / 10000
    error_code = data[19]
    frequency = struct.unpack('>i', data[31:35])[0] / 100

    line_id = data[37:40]
    line = 1 if line_id == b'\x00\x00\x00' else 2

    return {
        'line': line,
        'voltage': voltage,
        'current': current,
        'power': power,
        'energy': energy,
        'error_code': error_code,
        'frequency': frequency,
    }
```

---

## Gen 2 V2 Protocol (WD_V5 / WD_E5 / WD_V6 / WD_E6)

Used by Gen 2 WiFi + Bluetooth devices (EPOW models). Reverse engineered from Bluetooth HCI captures and the `com.yw.watchdog` Android application source code (`Cmd.java`, `Protocol.java`, `Package.java`, `DeviceManager.java`).

### GATT Profile

| Item | UUID |
|------|------|
| Service | `000000ff-0000-1000-8000-00805f9b34fb` |
| Characteristic (bidirectional) | `0000ff01-0000-1000-8000-00805f9b34fb` |

The single characteristic supports Read, Write, and Notify (properties: 0x1A).

### Connection Sequence

1. Connect to device via BLE
2. Enable notifications (write `0x0100` to CCCD)
3. Write initialization command: `!%!%,protocol,open,` (ASCII) to characteristic
4. Device begins streaming data packets as notifications
5. Packets arrive complete (no reassembly needed in most cases)

### Universal Packet Structure

Every V2 packet uses the same framing: 9-byte header + variable payload + 2-byte tail.

#### Header (9 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0-3 | 4 | Identifier | Magic header `24 79 77 40` (ASCII `$yw@`) |
| 4 | 1 | version | Protocol version (`0x01`) |
| 5 | 1 | msgId | Sequence number, increments 1-100 |
| 6 | 1 | cmd | Command ID (see Command Map) |
| 7-8 | 2 | dataLen | Payload length (big-endian). `0x0022`=34 single-block, `0x0044`=68 dual-block |

#### Tail (2 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| last 2 | 2 | Tail | Fixed `71 21` (ASCII `q!`) |

### Command Map

| Hex | Decimal | Name | Direction | Description |
|-----|---------|------|-----------|-------------|
| `0x01` | 1 | DLReport | Device -> App | Live sensor data |
| `0x02` | 2 | ErrorReport | Device -> App | Historical error logs |
| `0x03` | 3 | EnergyReset | App -> Device | Reset accumulated kWh to 0 |
| `0x04` | 4 | EnergyRestart | App -> Device | Soft restart of energy monitor |
| `0x05` | 5 | ErrorDel | App -> Device | Delete error log(s) |
| `0x06` | 6 | SetTime | App -> Device | Sync device clock |
| `0x07` | 7 | SetBacklight | App -> Device | Set LED brightness (0-5) |
| `0x08` | 8 | ReadStartTime | Bidirectional | Request/return session start time |
| `0x0A` | 10 | SetInitData | App -> Device | Initialization handshake |
| `0x0B` | 11 | SetOpen | App -> Device | Toggle main power relay |
| `0x0D` | 13 | NeutralDetection | App -> Device | Enable/disable ground monitoring |
| `0x0E` | 14 | Alarm | Device -> App | Immediate push-alert trigger |
| `0x31` | 49 | SubDeviceAdd | App -> Device | Pair wireless outlet sensor |
| `0x32` | 50 | SubDeviceDel | App -> Device | Unpair sub-device |
| `0x33` | 51 | SubDeviceList | Bidirectional | Request/return sub-device state |

### Standard Acknowledgment (ResultRes)

For commands like SetOpen, SetBacklight, NeutralDetection, the device responds with a 1-byte payload: `0x01` = Success, any other value = Fail.

### DLReport Data Packet (cmd 0x01)

**Payload:** 34 bytes per line (34 for 30A, 68 for 50A dual-block).

Each 34-byte block contains:

| Payload Offset | Size | Field | Format |
|---------------|------|-------|--------|
| 0-3 | 4 | Voltage | BE uint32 / 10000 (V) |
| 4-7 | 4 | Current | BE uint32 / 10000 (A) |
| 8-11 | 4 | Power | BE uint32 / 10000 (W) |
| 12-15 | 4 | Energy | BE uint32 / 10000 (kWh) |
| 16-19 | 4 | temp1 (reserved) | Not used by current firmware |
| 20-23 | 4 | Output Voltage | BE uint32 / 10000 (V) — booster models only |
| 24 | 1 | Backlight | LED brightness (0-5) |
| 25 | 1 | Neutral Detection | `0x00` = OK |
| 26 | 1 | Boost Mode | `0`=off, `1`=active — booster models only |
| 27 | 1 | Temperature | Degrees Celsius — booster models only |
| 28-31 | 4 | Frequency | BE uint32 / 100 (Hz) |
| 32 | 1 | Error Code | 0=OK, 1=E1, etc. |
| 33 | 1 | Relay Status | `0x00`=ON, `0x01`/`0x02`=OFF/Error |

**Absolute byte positions in the packet (including 9-byte header):**

| Bytes | Field | Notes |
|-------|-------|-------|
| 9-12 | Voltage (L1) | |
| 13-16 | Current (L1) | |
| 17-20 | Power (L1) | |
| 21-24 | Energy (L1) | |
| 25-28 | temp1 (reserved) | Firmware-reserved, not used. Per the TechBlueprints `PROTOCOL-GEN2.md`: "Temperature 1 (offset 16): Reserved; not used in current firmware." |
| 29-32 | Output Voltage | **Booster models only** (V8/V9/E8/E9). On V5/E5/V6/E6/V7/E7 the firmware repurposes these bytes to mirror the energy counter, so implementations must suppress this field on non-booster models. |
| 33 | Backlight | 0-5 |
| 34 | Neutral Detection | `0x00` = OK, non-zero = problem |
| 35 | Boost Mode | **Booster models only** (V8/V9/E8/E9). `0`=off, `1`=active. Reads `0` on non-booster models. |
| 36 | Temperature (°C) | **Booster models only** (V8/V9/E8/E9). Device internal temperature; reads `0` on non-booster models. Device firmware triggers an over-temp alarm at 74 °C. |
| 37-40 | Frequency (Hz) | BE uint32 / 100. E.g. 6000 = 60.00 Hz |
| 41 | Error Code | 0 = OK, 1-9 = E1-E9, 11-12 = F1-F2 |
| 42 | Relay Status | `0x00` = ON, `0x01`/`0x02` = OFF/tripped |

#### Dual-Block Layout (50A devices, payload length 0x0044 = 68 bytes)

For 50A devices, the packet contains two 34-byte blocks. Block 2 (Line 2) starts at byte 43:

| Bytes | Field |
|-------|-------|
| 43-46 | Voltage (L2) |
| 47-50 | Current (L2) |
| 51-54 | Power (L2) |
| 55-58 | Energy (L2) |
| 59-62 | temp1 (L2) |
| 63-66 | Output Voltage (L2) |
| 67 | Backlight (L2) |
| 68 | Neutral Detection (L2) |
| 69 | Boost Mode (L2) |
| 70 | Temperature (L2) |
| 71-74 | Frequency (L2) |
| 75 | Error Code (L2) |
| 76 | Relay Status (L2) |
| 77-78 | End Marker `q!` |

### ErrorReport (cmd 0x02)

**Payload:** Multiples of 16 bytes (16 bytes per error record).

| Payload Offset | Size | Field | Description |
|---------------|------|-------|-------------|
| 0-1 | 2 | Skipped | Padding |
| 2 | 1 | Record ID | Used when deleting |
| 3 | 1 | Skipped | Padding |
| 4-8 | 5 | Start Time | Year(+2000), Month, Day, Hour, Min |
| 9-13 | 5 | End Time | Year(+2000), Month, Day, Hour, Min |
| 14 | 1 | Skipped | Padding |
| 15 | 1 | Error Code | Error code ID |

### V2 Commands (App -> Device)

#### EnergyReset (0x03)
Empty payload. Resets accumulated kWh to 0.

#### ErrorDel (0x05)
1-byte payload: record ID to delete, or `0xFF` to delete all.

#### SetTime (0x06)
6-byte payload: `[YEAR-2000, MONTH+1, DAY, HOUR, MINUTE, SECOND]`

#### SetBacklight (0x07)
1-byte payload: `0x00` (off) to `0x05` (max brightness).

#### SetInitData (0x0A)
15-byte payload: 14-byte magic array + 1-byte device flag.
- Magic: `5E 68 84 21 2A 35 41 36 46 0A 02 1E 01 0A`
- Device flag: `0x01` for E6/V6 models, `0x5A` for all others

**Note:** The current integration uses `!%!%,protocol,open,` for initialization, which works. SetInitData may be more reliable but is not yet implemented.

#### SetOpen (0x0B)
1-byte payload: `0x01` = ON, `0x02` = OFF.

#### NeutralDetection (0x0D)
1-byte payload: `0x00` = enable monitoring, `0x01` = disable monitoring.

### Decoding Example (Python)

```python
import struct

def decode_v2_packet(data: bytes) -> dict:
    """Decode a Gen 2 V2 data packet."""
    if len(data) < 21 or data[0:4] != b'$yw@' or data[6] != 0x01:
        return None

    voltage = struct.unpack('>I', data[9:13])[0] / 10000
    current = struct.unpack('>I', data[13:17])[0] / 10000
    power = struct.unpack('>I', data[17:21])[0] / 10000

    result = {
        'voltage': voltage,
        'current': current,
        'power': power,
    }

    if len(data) >= 25:
        result['energy'] = struct.unpack('>I', data[21:25])[0] / 10000

    # Extended fields (bytes 25-42)
    if len(data) >= 43:
        result['output_voltage'] = struct.unpack('>I', data[29:33])[0] / 10000
        result['neutral_detection'] = data[34]
        result['boost_mode'] = data[35]
        result['temperature'] = data[36]
        result['frequency'] = struct.unpack('>I', data[37:41])[0] / 100
        result['error_code'] = data[41]
        result['relay_status'] = data[42]

    # Dual-block 50A packets (Line 2 at bytes 43-76)
    if len(data) >= 59 and data[7:9] == b'\x00\x44':
        result['line_2_voltage'] = struct.unpack('>I', data[43:47])[0] / 10000
        result['line_2_current'] = struct.unpack('>I', data[47:51])[0] / 10000
        result['line_2_power'] = struct.unpack('>I', data[51:55])[0] / 10000
        result['line_2_energy'] = struct.unpack('>I', data[55:59])[0] / 10000

    return result
```

---

## Open Questions

### Gen 1 V1 Protocol

| Item | Status |
|------|--------|
| **Command wire format** | **Unknown.** ASCII strings like `relayOn`, `reset`, `setTime`, `backLight`, `deleteAllRecord` are confirmed from the Android app, but the exact on-the-wire framing is not. Every combination tested so far (write-with/without-response to characteristics `0xfff5`, `0x1003`, `0x1005`, with and without `\r\n`) is accepted at the GATT layer but produces no visible effect on the device. The next step is to capture a live HCI trace from the official `powerwatchdog2` app while pressing a command button. |
| Chunk 2 bytes 20-30 (11 bytes) | Not parsed. Not parsed by the TechBlueprints reference either. Likely firmware-internal state. |
| Chunk 2 bytes 35-36 (2 bytes) | Not parsed, purpose unclear — sit between frequency and the line ID. |

### Gen 2 V2 Protocol

| Item | Status |
|------|--------|
| Sub-device commands (0x31-0x33) | Not implemented. For pairing wireless outlet sensors — no hardware available for testing. |
| Alarm push (0x0E) | Not implemented. Zero-payload push alert from device. |
| SetInitData (0x0A) | Not used. The integration's `!%!%,protocol,open,` init string works; SetInitData with the 15-byte magic array may be more robust but has not been needed. |
| Booster-only sensor validation | Output voltage, temperature, and boost mode are gated to V8/V9/E8/E9 models but have **not yet been validated against real booster hardware**. Seeking beta testers. |
| Neutral-detection control switch | The `NeutralDetection` (0x0D) command is implemented but has **not been validated** on a real device — needs beta testing. |

### Resolved Since Earlier Drafts

Several items previously listed as "unknown" have been clarified — primarily thanks to cross-referencing the [TechBlueprints/dbus-power-watchdog](https://github.com/TechBlueprints/dbus-power-watchdog) Venus OS implementation:

- **V2 bytes 25-28 (`temp1`):** firmware-reserved, not used. Previously listed as "purpose unknown."
- **V2 temperature (byte 36):** booster-model exclusive (V8/V9/E8/E9). Reads `0` on non-booster models; over-temp alarm fires at 74 °C.
- **V2 boost mode (byte 35):** booster-model exclusive. Reads `0` on non-booster models.
- **V2 output voltage (bytes 29-32):** confirmed to mirror the energy counter on V5/E5/V6/E6/V7/E7 and hold the real regulated voltage only on V8/V9/E8/E9. Now gated by `has_booster` in the integration.

---

## Protocol Detection Implementation

The integration detects which protocol to use through two mechanisms:

### 1. Name-Based Detection (Initial Guess)

At startup, the device name from the BLE advertisement is checked:
- Starts with `PMD`, `PWS`, or `PMS` -> Gen 1 V1 protocol
- Starts with `WD_V5`, `WD_E5`, `WD_V6`, or `WD_E6` -> Gen 2 V2 protocol

### 2. Service-Based Detection (Confirmation)

On the first BLE connection, the integration probes the device's advertised service UUIDs:
- Contains `000000ff-...` -> Gen 2 V2 protocol (confirmed)
- Contains `0000ffe0-...` -> Gen 1 V1 protocol (confirmed)
- Neither found -> Falls back to name-based guess with a warning

This two-step approach ensures correct protocol selection even if a future device uses an unexpected name prefix but a known BLE service.
