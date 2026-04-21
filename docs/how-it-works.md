# How It Works - Hughes Power Watchdog Integration

## File Structure

```
custom_components/hughes_power_watchdog/
  __init__.py        - Integration setup and teardown
  binary_sensor.py   - Binary sensor entities (relay, boost, neutral)
  brand/             - Device icons (icon.png, icon@2x.png) for HA UI
  button.py          - Button entities (energy reset, error delete)
  config_flow.py     - HA config flow for device discovery/setup
  const.py           - Constants, byte positions, sensor keys, command IDs, error codes
  coordinator.py     - BLE data coordinator (connection, parsing, commands, push updates)
  light.py           - Light entity (backlight brightness control)
  manifest.json      - HA integration manifest with BLE device name filters
  sensor.py          - Sensor entities (voltage, current, power, energy, etc.)
  strings.json       - UI strings for config flow (source for translations/en.json)
  switch.py          - Switch entities (monitoring, relay, neutral detection control)
  translations/      - Translated config flow strings (en.json)
  version.py         - Version string
```

## Module Descriptions

### `__init__.py`
Entry point for the integration. Creates the `HughesPowerWatchdogCoordinator` and forwards platform setup to sensor, binary_sensor, switch, button, and light modules.

### `const.py`
All constants organized by section:
- **Device name prefixes** - V1 (PMD/PWS/PMS) and V2 (WD_V5/WD_E5/WD_V6/WD_E6)
- **V1 protocol** - Service/characteristic UUIDs, byte positions for 40-byte data packets, frequency field (bytes 31-34), ASCII command strings (relayOn, reset, setTime, backLight, deleteAllRecord)
- **V2 protocol** - Service/characteristic UUID, framing constants ($yw@ header, q! tail), protocol version, sequence max, command IDs (0x01-0x0D), message types, byte positions for all single-block fields (bytes 9-42), dual-block Line 2 fields (bytes 43-76), relay/neutral payload values, ResultRes success code
- **Sensor keys** - String identifiers for all sensor types including backlight
- **Entity keys** - Switch (monitoring, relay, neutral detection control), button (energy reset, error delete), light (backlight)
- **Error codes** - E1-E9, F1-F2 mapping dict
- **Backlight ranges** - V1 max=4, V2 max=5

### `coordinator.py`
The core BLE data coordinator. Key responsibilities:
- **Protocol detection** - Two-step: name-based guess, then service UUID confirmation
- **Connection management** - Lock-protected connect/disconnect, exponential backoff retry
- **V1 notification handler** - Buffers two 20-byte chunks into 40-byte packets, extracts V/I/P/E/error/frequency, identifies Line 1 vs Line 2
- **V2 notification handler** - Parses $yw@ framed packets, extracts all fields including extended fields (output voltage, frequency, temperature, error code, relay status, boost mode, neutral detection, backlight). Also detects ResultRes acknowledgment packets for command responses.
- **V2 dual-block decoder** - Handles 79-byte packets from 50A devices with two 34-byte data blocks
- **Data dict builder** - Assembles all sensor values into dict for entity updates
- **Health monitor** - Background task detecting stale notifications for auto-reconnect
- **Command infrastructure** - Sequential command queue, V2 binary packet builder with sequence tracking and ack parsing, V1 ASCII command sender
- **Protocol-aware command methods** - `async_set_relay()`, `async_reset_energy()`, `async_sync_time()`, `async_set_backlight()`, `async_set_neutral_detection()`, `async_delete_errors()` — each routes to V1 or V2 implementation based on detected protocol
- **Auto clock sync** - Calls `async_sync_time()` on first connection for both V1 and V2

Key methods:
- `_detect_v2_by_name()` - Static, checks device name against V2 prefix list
- `_detect_protocol_by_service()` - Probes BLE service UUIDs
- `_notification_handler_v1()` / `_notification_handler_v2()` - Push notification callbacks
- `_parse_data_packet_v1()` - V1 40-byte packet parser
- `_parse_data_packet_v2()` - V2 variable-length packet parser, with ResultRes ack detection
- `_parse_v2_extended_fields()` - Extracts bytes 25-42 (output voltage [booster models only], freq, temp, error, relay, boost, neutral, backlight)
- `_decode_v2_dual_block_line2()` - Extracts Line 2 from dual-block 50A packets, stores L2 frequency
- `_build_data_dict()` - Assembles final sensor data dict; Line 2 keys only included when dual-line
- `_next_sequence()` - V2 sequence number (1-100 cycling)
- `_build_v2_command()` - Constructs $yw@ framed command packet
- `_send_v2_command()` - Sends V2 command, optionally waits for ResultRes ack (5s timeout)
- `_send_v1_command()` - Writes ASCII command to V1 command characteristic `0x1003` (write-with-response). Wire format still under investigation — writes currently succeed but the device ignores them, so V1 command entities are not exposed.

Key properties:
- `is_v2_protocol` - True for V2 devices (WD_V5/E5/V6/E6)
- `is_dual_line` - True when Line 2 data has been received (50A devices)
- `has_booster` - True for V8/V9/E8/E9 models that report real output voltage (V5/E5/V6/E6 mirror energy counter in that field)

### `sensor.py`
HA sensor entities:
- `HughesPowerWatchdogVoltageSensor` - Voltage (per-line)
- `HughesPowerWatchdogCurrentSensor` - Current (per-line)
- `HughesPowerWatchdogPowerSensor` - Power (per-line + combined)
- `HughesPowerWatchdogEnergySensor` - Cumulative kWh
- `HughesPowerWatchdogErrorCodeSensor` - Error code number
- `HughesPowerWatchdogErrorTextSensor` - Error description text
- `HughesPowerWatchdogFrequencySensor` - AC frequency (Hz)
- `HughesPowerWatchdogFrequencyLineSensor` - Per-line frequency (50A V2 dual-line only, Line 2)
- `HughesPowerWatchdogOutputVoltageSensor` - Output voltage (V2 booster models only: V8/V9/E8/E9)
- `HughesPowerWatchdogTemperatureSensor` - Temperature in Celsius (V2 booster models only; reads zero on non-booster models)

Sensor creation is gated by device capabilities:
- **All devices**: Line 1 V/I/P, energy, error code/text, frequency
- **Dual-line (50A) devices** (`coordinator.is_dual_line`): Line 2 V/I/P, combined power, frequency Line 2
- **V2 booster devices only** (`coordinator.is_v2_protocol and coordinator.has_booster`): Output voltage, Temperature (V5/E5/V6/E6 have no real values for these — output voltage mirrors the energy counter and temperature reads zero)

### `binary_sensor.py`
HA binary sensor entities (V2 protocol only):
- `HughesPowerWatchdogRelayStatusSensor` - Power relay ON/OFF (POWER device class)
- `HughesPowerWatchdogNeutralDetectionSensor` - Neutral problem detected (PROBLEM device class)
- `HughesPowerWatchdogBoostModeSensor` - Autoformer boost active/inactive. Only created for booster models (`coordinator.has_booster` → V8/V9/E8/E9).

### `button.py`
HA button entities (**V2 only** — V1 command support is work-in-progress):
- `HughesPowerWatchdogEnergyResetButton` - Resets cumulative kWh counter to zero
- `HughesPowerWatchdogErrorDeleteButton` - Deletes all stored error records from device

### `light.py`
HA light entity with brightness control (**V2 only** — V1 command support is work-in-progress):
- `HughesPowerWatchdogBacklightLight` - Device LED backlight brightness
  - Uses `ColorMode.BRIGHTNESS` (HA range 0-255)
  - Maps to discrete device levels: V2 = 0-5 (V1 = 0-4 when V1 commands are enabled)
  - To device: `round(ha_brightness / 255 * max_level)`
  - From device: `device_level / max_level * 255` (V2 reads from data stream byte 33)

### `switch.py`
HA switch entities:
- `HughesPowerWatchdogMonitoringSwitch` - Enables/disables BLE connection and data streaming (all devices)
- `HughesPowerWatchdogRelaySwitch` - Power relay on/off control (**V2 only** — V1 command support is work-in-progress)
- `HughesPowerWatchdogNeutralDetectionControlSwitch` - Enable/disable neutral detection monitoring (V2 only). Distinct from the NeutralDetection binary sensor which shows current status.

## Data Flow

```
BLE Device
  |
  | (BLE notifications, ~1s intervals)
  v
coordinator._notification_handler_v1/v2()
  |
  | (parse packet, extract fields)
  | (detect ResultRes acks for pending commands)
  v
coordinator._build_data_dict()
  |
  | (async_set_updated_data)
  v
HA CoordinatorEntity updates -> sensor/binary_sensor/switch/light entities

Commands (reverse direction):
  HA entity action (button press, switch toggle, light brightness)
  |
  v
coordinator.async_set_relay() / async_reset_energy() / async_set_backlight() / etc.
  |
  | (routes to V1 or V2 based on protocol)
  v
coordinator._send_v2_command() or _send_v1_command()
  |
  v
BLE write to device characteristic
```

## Protocol Summary

| Protocol | Packet Size | Encoding | Sensors |
|----------|-------------|----------|---------|
| V1 | 40 bytes (2x20 chunks) | Signed int32/10000 | V, I, P, E, error, frequency |
| V2 single-block | 45 bytes | Unsigned int32/10000 | V, I, P, E + output V, freq, temp, error, relay, boost, neutral, backlight |
| V2 dual-block | 79 bytes | Same | Same + Line 2 of all fields |

## Command Summary

V1 command wire format is unresolved — writes are accepted by the device but silently ignored. V1 command entities are not exposed in HA; the code paths remain for future work. See `docs/protocol.md` for details.

| Command | V1 (WIP — not exposed) | V2 | Entity Type |
|---------|------------------------|----|-------------|
| Relay on/off | `relayOn` (toggle) | SetOpen 0x0B (explicit on/off) | Switch (V2 only) |
| Energy reset | `reset` | EnergyReset 0x03 | Button (V2 only) |
| Clock sync | `setTime` | SetTime 0x06 | Auto on connect |
| Backlight | `backLight` + level (0-4) | SetBacklight 0x07 (0-5) | Light (V2 only) |
| Neutral detection | N/A | NeutralDetection 0x0D | Switch (V2 only) |
| Delete errors | `deleteAllRecord` | ErrorDel 0x05 (0xFF=all) | Button (V2 only) |

## Version History

See the [GitHub releases page](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/releases) for the full version history and per-release notes.
