# Hughes Power Watchdog BLE Protocol Documentation

This document describes the two Bluetooth Low Energy (BLE) protocols used by Hughes Power Watchdog devices:

- **Legacy protocol** - Used by Gen 1 devices (Bluetooth only, model suffix EPO)
- **V5 protocol** - Used by Gen 2 devices (WiFi + Bluetooth, model suffix EPOW)

## Device Generations

| Generation | Connectivity | Model Suffix | BLE Device Name | Mobile App |
|-----------|-------------|-------------|----------------|-----------|
| **Gen 1** | Bluetooth only | EPO | `PMD*`, `PWS*`, `PMS*` | [Power Watchdog Bluetooth ONLY](https://play.google.com/store/apps/details?id=com.hughes.epo) |
| **Gen 2** | WiFi + Bluetooth | EPOW | `WD_V5_*`, `WD_E5_*` | [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) |

The V5 protocol header `$yw@` corresponds to the `com.yw.watchdog` package name of the official Gen 2 WiFi app.

## Protocol Overview

| Feature | Gen 1 Legacy (PMD/PWS/PMS) | Gen 2 V5 (WD_V5/WD_E5) |
|---------|---------------------------|-------------------|
| Device Names | `PMD*`, `PWS*`, `PMS*` | `WD_V5_*`, `WD_E5_*` |
| Service UUID | `0000ffe0-0000-1000-8000-00805f9b34fb` | `000000ff-0000-1000-8000-00805f9b34fb` |
| TX Characteristic | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` |
| RX Characteristic | `0000fff5-0000-1000-8000-00805f9b34fb` | Same as TX (bidirectional) |
| Packet Header | `01 03 20` | `24 79 77 40` (`$yw@`) |
| Data Size | 40 bytes (2x20-byte chunks) | Variable, typically 45 bytes |
| Initialization | None (subscribe to notifications) | Send `!%!%,protocol,open,` |
| Line Support | Dual-line (50A models) | Single-line confirmed; dual-line speculative |
| Data Encoding | Big-endian signed int32 / 10000 | Big-endian unsigned int32 / 10000 |

## Protocol Detection

The integration uses a two-step detection approach:

1. **Name-based guess** (at startup): Checks device name prefix against known lists
2. **Service-based confirmation** (on first BLE connection): Probes the device's BLE service UUIDs to confirm the protocol

If the service detection disagrees with the name-based guess, the service result takes priority and a warning is logged.

---

## Gen 1 Legacy Protocol (PMD/PWS/PMS)

Used by Gen 1 Bluetooth-only devices (EPO models). Based on the ESPHome implementation by spbrogan, tango2590, and makifoxgirl.

Source: https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog

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

#### Chunk 1 (bytes 0-19)

| Offset | Size | Field | Format |
|--------|------|-------|--------|
| 0-2 | 3 | Header | `01 03 20` (identifies data packets) |
| 3-6 | 4 | Voltage | Big-endian signed int32 / 10000 (volts) |
| 7-10 | 4 | Current | Big-endian signed int32 / 10000 (amps) |
| 11-14 | 4 | Power | Big-endian signed int32 / 10000 (watts) |
| 15-18 | 4 | Energy | Big-endian signed int32 / 10000 (kWh) |
| 19 | 1 | Error Code | Unsigned byte (see error code table) |

#### Chunk 2 (bytes 20-39)

| Offset | Size | Field | Format |
|--------|------|-------|--------|
| 20-36 | 17 | Unknown | Purpose not decoded |
| 37-39 | 3 | Line ID | `00 00 00` = Line 1, `01 01 01` = Line 2 |

### Dual-Line Support

50A Gen 1 devices (e.g., PWD50-EPD) send separate data packets for each line. Each packet includes a Line ID (bytes 37-39) to identify which line the data belongs to:

- `00 00 00` = Line 1
- `01 01 01` = Line 2

30A devices send only Line 1 data.

### Error Codes

| Code | Description |
|------|-------------|
| 0 | No Error |
| 1 | Open Ground |
| 2 | Reverse Polarity |
| 3 | Open Neutral |
| 4 | High Voltage |
| 5 | Low Voltage |
| 6 | High Voltage Surge |
| 7 | Frequency Error |

### Decoding Example (Python)

```python
import struct

def decode_legacy_packet(data: bytes) -> dict:
    """Decode a 40-byte Gen 1 Legacy data packet."""
    if len(data) < 40:
        return None

    # Verify header
    if data[0:3] != b'\x01\x03\x20':
        return None  # Not a data packet

    voltage = struct.unpack('>i', data[3:7])[0] / 10000
    current = struct.unpack('>i', data[7:11])[0] / 10000
    power = struct.unpack('>i', data[11:15])[0] / 10000
    energy = struct.unpack('>i', data[15:19])[0] / 10000
    error_code = data[19]

    # Line identification
    line_id = data[37:40]
    line = 1 if line_id == b'\x00\x00\x00' else 2

    return {
        'line': line,
        'voltage': voltage,
        'current': current,
        'power': power,
        'energy': energy,
        'error_code': error_code,
    }
```

---

## Gen 2 V5 Protocol (WD_V5 / WD_E5)

Used by Gen 2 WiFi + Bluetooth devices (EPOW models). Reverse engineered from Bluetooth HCI captures of a WD_V5 device (device name: `WD_V5_9e9e6e20b9ed`).

### GATT Profile

| Item | UUID |
|------|------|
| Service | `000000ff-0000-1000-8000-00805f9b34fb` |
| Characteristic (bidirectional) | `0000ff01-0000-1000-8000-00805f9b34fb` |

The single characteristic supports Read, Write, and Notify (properties: 0x1A).

- **CCCD Handle**: 0x002B
- **Characteristic Handle**: 0x002A

### Connection Sequence

1. Connect to device via BLE
2. Enable notifications (write `0x0100` to CCCD at handle 0x002B)
3. Write initialization command: `!%!%,protocol,open,` (ASCII) to characteristic
4. Device begins streaming data packets as notifications
5. Packets arrive complete (no reassembly needed in most cases)

### Message Types

All V5 packets share a common framing:

| Offset | Size | Field |
|--------|------|-------|
| 0-3 | 4 | Header: `$yw@` (hex: `24 79 77 40`) |
| 4 | 1 | Unknown (always `0x01`) |
| 5 | 1 | Sequence number (incrementing) |
| 6 | 1 | Message type |
| last 2 | 2 | End marker: `q!` (hex: `71 21`) |

Three message types have been observed:

| Type | Value | Description |
|------|-------|-------------|
| Data | `0x01` | Power measurement data (45 or 79 bytes observed) |
| Status | `0x02` | Status/info packet (24-27 bytes) |
| Control | `0x06` | Protocol handshake/acknowledgment |

### Data Packet Structure (Type 0x01)

Two payload layouts have been observed:

- **Single-block layout** (`bytes 7-8 = 0x0022`, 45-byte packet)
- **Dual-block layout** (`bytes 7-8 = 0x0044`, 79-byte packet, used by tested Gen 2 50A devices)

#### Single-Block Layout (45 bytes)

| Offset | Size | Field | Format | Status |
|--------|------|-------|--------|--------|
| 0-3 | 4 | Header | ASCII `$yw@` | Decoded |
| 4 | 1 | Unknown | Always `0x01` | Unknown |
| 5 | 1 | Sequence | Incrementing counter | Decoded |
| 6 | 1 | Message Type | `0x01` = data | Decoded |
| 7-8 | 2 | Unknown | Always `0x0022` (34) | Unknown |
| **9-12** | 4 | **Voltage (L1)** | BE uint32 / 10000 (volts) | **Decoded** |
| **13-16** | 4 | **Current (L1)** | BE uint32 / 10000 (amps) | **Decoded** |
| **17-20** | 4 | **Power (L1)** | BE uint32 / 10000 (watts) | **Decoded** |
| **21-24** | 4 | **Energy** | BE uint32 / 10000 (kWh) | **Decoded** |
| 25-28 | 4 | Voltage (L2)? | BE uint32 / 10000 (speculative) | Speculative |
| 29-32 | 4 | Current (L2)? | BE uint32 / 10000 (speculative) | Speculative |
| 33-36 | 4 | Power (L2)? | BE uint32 / 10000 (speculative) | Speculative |
| 37-40 | 4 | Frequency? | ~6000 = 60.00 Hz? | Unconfirmed |
| 41-42 | 2 | Error code? | 0 in all captures | Unconfirmed |
| 43-44 | 2 | End Marker | ASCII `q!` | Decoded |

#### Dual-Block Layout (79 bytes, validated on Gen 2 50A)

| Offset | Size | Field | Format | Status |
|--------|------|-------|--------|--------|
| 0-3 | 4 | Header | ASCII `$yw@` | Decoded |
| 4 | 1 | Unknown | Always `0x01` | Unknown |
| 5 | 1 | Sequence | Incrementing counter | Decoded |
| 6 | 1 | Message Type | `0x01` = data | Decoded |
| 7-8 | 2 | Length | `0x0044` (68) | Decoded |
| **9-12** | 4 | **Voltage (L1)** | BE uint32 / 10000 | **Decoded** |
| **13-16** | 4 | **Current (L1)** | BE uint32 / 10000 | **Decoded** |
| **17-20** | 4 | **Power (L1)** | BE uint32 / 10000 | **Decoded** |
| **21-24** | 4 | **Energy (L1)** | BE uint32 / 10000 | **Decoded** |
| 25-42 | 18 | Unknown per-block fields | Vendor-specific | Partial |
| **43-46** | 4 | **Voltage (L2)** | BE uint32 / 10000 | **Decoded** |
| **47-50** | 4 | **Current (L2)** | BE uint32 / 10000 | **Decoded** |
| **51-54** | 4 | **Power (L2)** | BE uint32 / 10000 | **Decoded** |
| **55-58** | 4 | **Energy (L2)** | BE uint32 / 10000 | **Decoded** |
| 59-76 | 18 | Unknown / per-block trailing fields | Vendor-specific | Partial |
| 77-78 | 2 | End Marker | ASCII `q!` | Decoded |

### Line 2 Detection

For single-phase (30A) devices, only Line 1 data is valid. Bytes 25-36 contain non-voltage values for these devices.

For validated Gen 2 50A dual-phase devices using the 79-byte dual-block layout (`0x0044`), Line 2 is decoded from bytes 43-58 (V/I/P/E).

For other V5 layouts, the integration still includes fallback decoding for bytes 25-36 when those values are plausible.

### Status Packet (Type 0x02, 24-27 bytes)

| Offset | Size | Field |
|--------|------|-------|
| 0-3 | 4 | Header `$yw@` |
| 4 | 1 | Unknown (`0x01`) |
| 5 | 1 | Sequence |
| 6 | 1 | Message Type (`0x02`) |
| 7+ | var | Status data (contains ASCII "Er" - may indicate error status) |

Status packets appear to have constant content during normal operation.

### Control Packet (Type 0x06)

Control/acknowledgment packets are used for protocol handshaking:

```
24797740 01 02 06 0001 01 7121
```

### Write Commands

Commands sent to the device follow the same `$yw@` framing:

```
24797740 01 02 06 00 06 1a 02 02 0a 28 15 7121
  ^        ^  ^  ^                         ^
  |        |  |  |                         |
Header   Unk Seq Type                  End Marker
```

The command payload format beyond initialization has not been decoded.

### Sample Readings

From real device captures:

| Voltage | Current | Power | Load |
|---------|---------|-------|------|
| 121.54 V | 4.53 A | 531.45 W | Light |
| 121.55 V | 4.90 A | 576.95 W | Light |
| 119.37 V | 14.01 A | 1666.74 W | Heavy |
| 119.35 V | 13.99 A | 1665.11 W | Heavy |

### Decoding Example (Python)

```python
import struct

def decode_v5_packet(data: bytes) -> dict:
    """Decode a Gen 2 V5 data packet."""
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

    # Energy (L1, bytes 21-24)
    if len(data) >= 25:
        result['energy'] = struct.unpack('>I', data[21:25])[0] / 10000

    # Dual-block 50A packets include Line 2 at bytes 43-58.
    if len(data) >= 59 and data[7:9] == b'\x00\x44':
        result['line_2_voltage'] = struct.unpack('>I', data[43:47])[0] / 10000
        result['line_2_current'] = struct.unpack('>I', data[47:51])[0] / 10000
        result['line_2_power'] = struct.unpack('>I', data[51:55])[0] / 10000
        result['line_2_energy'] = struct.unpack('>I', data[55:59])[0] / 10000

    return result
```

---

## What We Don't Know Yet

### Gen 1 Legacy Protocol

| Item | Notes |
|------|-------|
| Bytes 20-36 (Chunk 2) | 17 bytes of unknown data between chunks |
| Additional packet types | Only the `01 03 20` header data packet is decoded |
| Write commands | The RX characteristic exists but no command protocol is documented |

### Gen 2 V5 Protocol

| Item | Notes |
|------|-------|
| Byte 4 | Always `0x01` - purpose unknown |
| Bytes 7-8 | Packet length field (`0x0022` single-block, `0x0044` dual-block observed) |
| Bytes 25-36 on single-phase devices | Values present but not voltage/current/power for these devices |
| Bytes 25-36 on dual-phase devices | Used as fallback only; primary validated L2 offsets for tested 50A devices are 43-58 in dual-block packets |
| Bytes 37-40 | Value ~6000, likely frequency (60.00 Hz) but unconfirmed |
| Bytes 41-42 | Value 0 in all captures, likely error code but mapping unknown |
| Error code mapping | Gen 2 may use the same codes as Gen 1 (0-7) or different codes |
| Status packet (0x02) payload | Contains "Er" string but full format unknown |
| Control packet (0x06) payload | Handshake protocol not fully decoded |
| Write command format | Beyond `!%!%,protocol,open,`, no commands documented |
| Authentication | No authentication observed in captures; app works in airplane mode (BT only) |

### Testing Needed

- **Gen 2 error states**: Need captures during fault conditions to decode error fields
- **Gen 2 frequency**: Need confirmation that bytes 37-40 represent AC frequency
- **New device models**: Any future Hughes models may use either protocol or introduce a new one

---

## Protocol Detection Implementation

The integration detects which protocol to use through two mechanisms:

### 1. Name-Based Detection (Initial Guess)

At startup, the device name from the BLE advertisement is checked:
- Starts with `PMD`, `PWS`, or `PMS` -> Gen 1 Legacy protocol
- Starts with `WD_V5` or `WD_E5` -> Gen 2 V5 protocol

### 2. Service-Based Detection (Confirmation)

On the first BLE connection, the integration probes the device's advertised service UUIDs:
- Contains `000000ff-...` -> Gen 2 V5 protocol (confirmed)
- Contains `0000ffe0-...` -> Gen 1 Legacy protocol (confirmed)
- Neither found -> Falls back to name-based guess with a warning

This two-step approach ensures correct protocol selection even if a future device uses an unexpected name prefix but a known BLE service.
