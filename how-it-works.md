# How It Works - Hughes Power Watchdog Integration

This document describes the architecture, files, modules, and functions of the Hughes Power Watchdog Home Assistant integration.

## Project Overview

This is a custom Home Assistant integration that provides direct Bluetooth Low Energy (BLE) connectivity to Hughes Power Watchdog surge protectors (PWD/PWS models). It eliminates the need for an ESP32 bridge device by connecting directly from Home Assistant to the Hughes device via BLE.

The integration uses a persistent BLE connection pattern with command queue support, enabling future two-way communication for device control while maintaining efficient resource usage through intelligent idle timeout management.

---

## Directory Structure

```
My-Hughes-Power-Watchdog/
├── custom_components/
│   └── hughes_power_watchdog/     # Main integration package
│       ├── __init__.py            # Integration initialization
│       ├── config_flow.py         # UI configuration flow
│       ├── const.py               # Constants and configuration
│       ├── coordinator.py         # BLE data coordinator
│       ├── manifest.json          # Integration metadata
│       ├── sensor.py              # Sensor entities
│       ├── strings.json           # UI translations
│       ├── switch.py              # Switch entities
│       └── version.py             # Version information
├── Original_Starting_Point/       # Reference ESPHome implementation
├── tasks/                         # Development task tracking
├── .env.example                   # Environment template
├── .gitignore                     # Git exclusions
├── CLAUDE.md                      # Development guidelines
├── config.yaml.example            # Configuration template
├── hacs.json                      # HACS metadata
└── README.md                      # User documentation
```

---

## Core Integration Files

### 1. `manifest.json`

**Purpose**: Defines integration metadata for Home Assistant

**Key Components**:
- `domain`: "hughes_power_watchdog" - Unique identifier for the integration
- `name`: "Hughes Power Watchdog" - Display name
- `codeowners`: ["@kellym"] - Code maintainers
- `config_flow`: true - Enables UI-based configuration
- `dependencies`: [] - No HA component dependencies
- `documentation`: GitHub repository URL
- `iot_class`: "local_polling" - Indicates local device polling
- `requirements`: ["bleak-retry-connector>=3.5.0"] - For reliable BLE connection establishment
- `version`: "0.3.2" - Current version
- `bluetooth`: Defines auto-discovery patterns for PMD* and PWS* devices

**How It Works**:
- Home Assistant reads this file to understand integration capabilities
- The `bluetooth` section enables automatic discovery of Hughes devices
- Uses `bleak-retry-connector` for reliable connection establishment (HA recommended approach)
- Uses HA's `bluetooth.async_ble_device_from_address()` for proxy compatibility

**Architecture Decision (v0.3.2)**:
- Uses `establish_connection()` from bleak-retry-connector (HA best practice)
- Provides reliable connection establishment with automatic retries
- Compatible with ESP32 Bluetooth proxies
- Follows Home Assistant guidelines for BLE integrations

---

### 2. `version.py`

**Purpose**: Centralized version management

```python
VERSION = "0.3.2"
```

**How It Works**:
- Single source of truth for version number
- Follows semantic versioning (MAJOR.MINOR.PATCH)
- Can be imported by other modules if needed
- Should be updated before every commit per CLAUDE.md guidelines

**Version History**:
- 0.1.0: Initial structure with placeholders
- 0.2.0: BLE coordinator implementation with bleak-retry-connector
- 0.3.0: Persistent connection architecture with command queue support
- 0.3.1: Fix BLE connection and device registry issues
- 0.3.2: Fix BLE connection warnings (use establish_connection), reduce header log noise

---

### 3. `const.py`

**Purpose**: Defines all constants used throughout the integration

**Key Constants**:

```python
DOMAIN = "hughes_power_watchdog"
NAME = "Hughes Power Watchdog"
```
- Domain identifier used throughout Home Assistant

```python
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]
```
- Defines which entity platforms this integration provides

```python
CONF_MAC_ADDRESS = "mac_address"
```
- Configuration key for storing the device's MAC address

```python
DEVICE_NAME_PMD = "PMD"
DEVICE_NAME_PWS = "PWS"
```
- Prefixes for device names used in Bluetooth discovery

```python
DEFAULT_SCAN_INTERVAL = 30  # seconds
```
- How often to poll the device for updates

**Connection Management Constants (v0.3.0)**:
```python
CONNECTION_IDLE_TIMEOUT = 120  # seconds - disconnect after this much idle time
CONNECTION_MAX_ATTEMPTS = 3    # Maximum connection retry attempts
CONNECTION_MAX_DELAY = 6.0     # Maximum retry delay in seconds
CONNECTION_DELAY_REDUCTION = 0.75  # Multiply delay by this on success
DATA_COLLECTION_TIMEOUT = 3    # seconds - wait for device to send data chunks
```
- **CONNECTION_IDLE_TIMEOUT**: Persistent connection is maintained for 120 seconds of inactivity
- **CONNECTION_MAX_ATTEMPTS**: Retry connection up to 3 times before failing
- **CONNECTION_MAX_DELAY**: Exponential backoff caps at 6 seconds
- **CONNECTION_DELAY_REDUCTION**: Successful operations reduce delay by 25%
- **DATA_COLLECTION_TIMEOUT**: Wait 3 seconds for device to send complete data packet

```python
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID_TX = "0000ffe2-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID_RX = "0000fff5-0000-1000-8000-00805f9b34fb"
```
- **SERVICE_UUID**: Main BLE service for Hughes Power Watchdog
- **CHARACTERISTIC_UUID_TX**: Device transmits data (notifications from device to HA)
- **CHARACTERISTIC_UUID_RX**: Device receives commands (writes from HA to device - future use)
- Source: Extracted from ESPHome implementation

```python
# Data Protocol Constants
CHUNK_SIZE = 20
TOTAL_DATA_SIZE = 40
HEADER_BYTES = b"\x01\x03\x20"
DATA_CONVERSION_FACTOR = 10000
```
- Device sends 40 bytes in two 20-byte chunks
- Header identifies start of data packet
- Values are big-endian int32 divided by 10,000

**Data Packet Structure**:

Chunk 1 (bytes 0-19):
- Bytes 0-2: Header `01 03 20`
- Bytes 3-6: Voltage (V)
- Bytes 7-10: Current (A)
- Bytes 11-14: Power (W)
- Bytes 15-18: Cumulative Energy (kWh)
- Byte 19: Error code

Chunk 2 (bytes 20-39):
- Bytes 37-39: Line identifier
  - `00 00 00` = Line 1 (30A systems only have Line 1)
  - `01 01 01` = Line 2 (50A systems have both)

```python
SENSOR_VOLTAGE_L1 = "voltage_line_1"
SENSOR_CURRENT_L1 = "current_line_1"
# ... etc
```
- Unique identifiers for each sensor type

**How It Works**:
- Provides a single place to manage all constants
- Prevents magic strings scattered throughout code
- Makes it easy to update values globally

---

### 4. `coordinator.py`

**Purpose**: Manages BLE communication and data updates using Home Assistant's DataUpdateCoordinator with persistent connection architecture

**Class: HughesPowerWatchdogCoordinator**

Inherits from `DataUpdateCoordinator[dict[str, Any]]` to provide centralized data management.

**Architecture (v0.3.0)**:
The coordinator uses a persistent BLE connection pattern with:
- **Persistent Connection**: Maintains connection with 120-second idle timeout
- **Command Queue**: `asyncio.Queue` for serialized command execution (future two-way communication)
- **Connection Health Monitor**: Background task that disconnects idle connections
- **Command Worker**: Background task that processes commands sequentially
- **Adaptive Retry Logic**: Exponential backoff on failures, gradual reduction on success

**Attributes**:

**Device Information**:
- `address`: MAC address of Hughes device
- `device_name`: Friendly name for the device
- `config_entry`: ConfigEntry reference for unique IDs and device info

**Data Buffers**:
- `_data_buffer`: Buffer for collecting 40-byte data packets
- `_line_1_data`: Parsed Line 1 measurements
- `_line_2_data`: Parsed Line 2 measurements (50A units only)
- `_error_code`: Current error code from device

**Connection Management**:
- `_client`: BleakClient instance (persistent)
- `_connection_lock`: asyncio.Lock to prevent concurrent connection attempts
- `_last_activity_time`: Timestamp of last BLE activity for idle timeout

**Command Queue System**:
- `_command_queue`: asyncio.Queue for command serialization
- `_command_worker_task`: Background task processing commands
- `_health_monitor_task`: Background task monitoring connection health

**Adaptive Retry**:
- `_connect_delay`: Current connection retry delay (exponential backoff)
- `_read_delay`: Current read retry delay (reserved for future use)

**Methods**:

#### `__init__(hass, config_entry)`
```python
def __init__(
    self,
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
```

**What It Does**:
- Initializes coordinator with 30-second update interval
- Sets up data buffers for packet reassembly
- Initializes connection management attributes
- Creates command queue for future two-way communication
- Starts background tasks (command worker, health monitor)

**Background Tasks**:
- Command worker: Processes commands from queue sequentially
- Health monitor: Disconnects connections idle for >120 seconds

#### `_start_background_tasks()`
```python
def _start_background_tasks(self) -> None:
```

**What It Does**:
- Starts command worker task if not already running
- Starts connection health monitor task if not already running
- Called during coordinator initialization

**How It Works**:
- Uses `asyncio.create_task()` to create background tasks
- Tasks run for the lifetime of the coordinator
- Canceled during `async_disconnect()`

#### `device_info` (property)
```python
@property
def device_info(self) -> DeviceInfo:
```

**What It Does**:
- Returns DeviceInfo for Home Assistant device registry
- Associates all entities with a single device
- Includes manufacturer, model, and Bluetooth connection info

**How It Works**:
- All sensor and switch entities reference this property
- Creates unified device in HA UI with all entities grouped together

#### `async _ensure_connected()`
```python
async def _ensure_connected(self) -> BleakClient:
```

**What It Does**:
1. Returns existing connection if still valid
2. Gets BLEDevice using `bluetooth.async_ble_device_from_address()` (proxy-compatible)
3. Creates BleakClient and connects
4. Implements retry logic with exponential backoff
5. Updates last activity time on success
6. Reduces connection delay on successful connection

**How It Works**:
- Uses connection lock to prevent concurrent connection attempts
- Retries up to `CONNECTION_MAX_ATTEMPTS` times
- Delay starts at 1s and doubles each attempt (1s → 2s → 4s → 6s max)
- Successful connection reduces delay by 25% for next time
- After sustained success, delay resets to 0
- Raises `UpdateFailed` if all attempts fail

**Proxy Compatibility**:
- Uses HA's `bluetooth.async_ble_device_from_address()`
- Automatically finds nearest adapter or ESP32 proxy
- Works seamlessly with ESPHome Bluetooth proxies

#### `async _disconnect()`
```python
async def _disconnect(self) -> None:
```

**What It Does**:
- Disconnects BLE client if connected
- Cleans up client reference
- Uses connection lock for thread safety

**How It Works**:
- Called by health monitor when connection idle >120 seconds
- Called during integration unload
- Handles errors gracefully (logs but doesn't raise)

#### `async _monitor_connection_health()`
```python
async def _monitor_connection_health(self) -> None:
```

**What It Does**:
- Background task running for lifetime of coordinator
- Checks every 30 seconds if connection is idle
- Disconnects if idle time exceeds 120 seconds
- Handles CancelledError for graceful shutdown

**How It Works**:
- Infinite loop with 30-second sleep
- Calculates idle time: `time.time() - self._last_activity_time`
- Calls `_disconnect()` if idle too long
- Frees BLE connection slot for other integrations/apps

**Resource Efficiency**:
- Persistent connection during active use
- Automatic cleanup when idle
- Prevents resource exhaustion on ESP32 proxies

#### `async _process_commands()`
```python
async def _process_commands(self) -> None:
```

**What It Does**:
- Background task processing command queue
- Waits for commands from `execute_command()`
- Ensures connection before executing command
- Executes command function with BleakClient
- Immediately requests device status after command (for UI feedback)
- Handles errors and sets future result/exception

**How It Works**:
- Infinite loop waiting on `_command_queue.get()`
- Each queue item is tuple: `(command_func, future)`
- Calls `command_func(client)` with connected BleakClient
- Sets `future.set_result()` or `future.set_exception()`
- Marks task done via `queue.task_done()`

**Command Serialization**:
- Prevents concurrent BLE operations
- Ensures device sees one command at a time
- Critical for future two-way communication

#### `async execute_command(command_func)`
```python
async def execute_command(self, command_func: Callable) -> Any:
```

**What It Does**:
- Public method to queue a command for execution
- Creates future for result
- Queues command with future
- Waits for and returns result

**Parameters**:
- `command_func`: Async function taking BleakClient, returning result

**How It Works**:
- Command worker picks up from queue
- Executes serially with other commands
- Returns result from future
- Future use for device control commands

**Example Usage (future)**:
```python
async def set_voltage_threshold(client, voltage):
    await client.write_gatt_char(CHARACTERISTIC_UUID_RX, data)
    return True

result = await coordinator.execute_command(
    lambda client: set_voltage_threshold(client, 125)
)
```

#### `async _request_device_status()`
```python
async def _request_device_status(self) -> None:
```

**What It Does**:
1. Ensures connection is active
2. Clears data buffer
3. Subscribes to TX characteristic for notifications
4. Waits 3 seconds for device to send data (two 20-byte chunks)
5. Unsubscribes from notifications
6. Updates last activity timestamp

**How It Works**:
- Called by `_async_update_data()` during polling
- Called by command worker after executing commands
- Device automatically sends data when subscribed to TX characteristic
- Notification handler receives chunks and assembles packet

#### `async _async_update_data()`
```python
async def _async_update_data(self) -> dict[str, Any]:
```

**What It Does**:
1. Checks if commands are pending in queue
2. Returns cached data if commands pending (yields to commands)
3. Otherwise, requests device status
4. Returns parsed data dictionary

**How It Works**:
- Called automatically by coordinator every 30 seconds
- Polling yields to command queue - commands have priority
- Uses persistent connection (no connect/disconnect overhead)
- Raises `UpdateFailed` if data collection fails

**Command Queue Priority**:
- If `_command_queue.empty()` is False, skip polling
- Returns existing data to avoid interfering with commands
- Ensures responsive command execution

#### `_notification_handler(sender, data)`
```python
def _notification_handler(self, sender: int, data: bytearray) -> None:
```

**What It Does**:
1. Receives 20-byte chunks from BLE characteristic
2. Appends data to buffer
3. Calls `_parse_data_packet()` when 40 bytes received
4. Clears buffer after parsing

**How It Works**:
- Callback function registered with `client.start_notify()`
- Device sends two sequential 20-byte notifications
- Buffer reassembles into complete 40-byte packet

#### `_parse_data_packet()`
```python
def _parse_data_packet(self) -> None:
```

**What It Does**:
1. Verifies header bytes (`01 03 20`)
2. Extracts big-endian int32 values from byte positions
3. Divides by 10,000 to get decimal values
4. Identifies Line 1 vs Line 2 based on bytes 37-39
5. Stores in `_line_1_data` or `_line_2_data`

**Data Extraction**:
- Bytes 3-6: Voltage → `struct.unpack(">i", bytes)[0] / 10000`
- Bytes 7-10: Current → same conversion
- Bytes 11-14: Power → same conversion
- Bytes 15-18: Energy → same conversion
- Byte 19: Error code (no conversion)

**Line Identification**:
- Bytes 37-39 = `00 00 00` → Line 1
- Bytes 37-39 = `01 01 01` → Line 2

#### `_build_data_dict()`
```python
def _build_data_dict(self) -> dict[str, Any]:
```

**What It Does**:
- Combines Line 1 and Line 2 data into single dictionary
- Maps internal data to sensor keys
- Calculates combined power for 50A units
- Maps error codes to descriptive text
- Returns data dict for entity updates

**Data Dictionary Structure**:
```python
{
    "voltage_line_1": float,
    "current_line_1": float,
    "power_line_1": float,
    "voltage_line_2": float | None,  # None for 30A
    "current_line_2": float | None,
    "power_line_2": float | None,
    "combined_power": float,
    "total_power": float,  # cumulative kWh
    "error_code": int,
    "error_text": str,
}
```

#### `async_disconnect()`
```python
async def async_disconnect(self) -> None:
```

**What It Does**:
1. Cancels command worker task
2. Cancels health monitor task
3. Waits for tasks to finish
4. Disconnects from BLE device

**How It Works**:
- Called during integration unload
- Ensures all background tasks stopped
- Cleans up BLE connection
- Graceful shutdown of coordinator

**Error Code Mapping**:
```python
ERROR_CODES = {
    0: "No Error",
    1: "Open Ground",
    2: "Reverse Polarity",
    3: "Open Neutral",
    4: "High Voltage",
    5: "Low Voltage",
    6: "High Voltage Surge",
    7: "Frequency Error",
}
```

**How It Works (v0.3.0 Architecture)**:
- Coordinator maintains persistent BLE connection
- Background health monitor disconnects after 120 seconds idle
- Command queue ready for future two-way communication
- Polling yields to commands for responsive control
- Adaptive retry logic handles connection failures gracefully
- Data is cached and shared with all sensor entities
- Entities automatically update when coordinator refreshes
- No external dependencies - uses HA's bluetooth component directly

---

### 5. `__init__.py`

**Purpose**: Integration initialization and entry point for Home Assistant

**Functions**:

#### `async_setup_entry(hass, entry)`
```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hughes Power Watchdog from a config entry."""
```

**What It Does**:
1. Called when a user adds the integration via UI
2. Extracts config entry (contains device address)
3. Creates `HughesPowerWatchdogCoordinator` instance with config_entry
4. Performs initial data fetch with `async_config_entry_first_refresh()`
5. Stores coordinator in `hass.data[DOMAIN][entry.entry_id]`
6. Forwards setup to platform modules (sensor, switch)
7. Returns True if successful

**Parameters**:
- `hass`: Home Assistant instance
- `entry`: Configuration entry containing device address

**Key Changes in v0.3.0**:
- Coordinator receives entire config_entry (not just address/name)
- Coordinator starts background tasks automatically
- Initial refresh establishes persistent connection

#### `async_unload_entry(hass, entry)`
```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
```

**What It Does**:
1. Called when integration is removed
2. Retrieves coordinator from hass.data
3. Calls `coordinator.async_disconnect()` to clean up
4. Unloads all platforms
5. Removes coordinator from hass.data
6. Returns True if successful

**Cleanup Process (v0.3.0)**:
- Cancels background tasks (command worker, health monitor)
- Disconnects persistent BLE connection
- Frees all resources

**How It Works**:
- Home Assistant calls these functions during integration lifecycle
- Setup initializes coordinator and platforms
- Unload performs complete cleanup
- Uses `async_forward_entry_setups` to delegate to platform files

---

### 6. `config_flow.py`

**Purpose**: Handles UI-based device discovery and configuration

**Class: HughesPowerWatchdogConfigFlow**

Inherits from `config_entries.ConfigFlow` to provide configuration UI.

**Attributes**:
- `VERSION = 1`: Config flow version
- `_discovered_devices`: Dict of discovered BLE devices
- `_discovery_info`: Current device being configured

**Methods**:

#### `async_step_bluetooth(discovery_info)`
```python
async def async_step_bluetooth(
    self, discovery_info: BluetoothServiceInfoBleak
) -> FlowResult:
```

**What It Does**:
1. Called automatically when Home Assistant discovers a matching Bluetooth device
2. Sets unique ID based on MAC address
3. Aborts if device already configured
4. Proceeds to confirmation step

**How It Works**:
- Home Assistant's Bluetooth integration detects devices matching manifest.json patterns
- This method is triggered automatically
- Prevents duplicate configurations

#### `async_step_bluetooth_confirm(user_input)`
```python
async def async_step_bluetooth_confirm(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
```

**What It Does**:
1. Shows confirmation dialog to user
2. If confirmed, creates config entry with device address
3. Integration is then added to Home Assistant

**Returns**:
- Form for user confirmation, or
- Config entry creation upon confirmation

#### `async_step_user(user_input)`
```python
async def async_step_user(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
```

**What It Does**:
1. Manual setup flow (when user adds integration manually)
2. Scans for nearby Hughes devices
3. Presents list of discovered devices
4. User selects device to configure

**How It Works**:
- Calls `async_discovered_service_info(self.hass)` to get all discovered BLE devices
- Filters for Hughes devices using `_is_hughes_device()`
- Shows dropdown of available devices
- Creates config entry when user selects device

#### `_is_hughes_device(name)` (static method)
```python
@staticmethod
def _is_hughes_device(name: str | None) -> bool:
```

**What It Does**:
- Checks if device name starts with "PMD" or "PWS"
- Returns True if it's a Hughes device

**How It Works**:
- Simple string matching against known device name patterns
- Used to filter Bluetooth devices

---

### 7. `strings.json`

**Purpose**: UI text and translations for configuration flow

**Structure**:

```json
{
  "config": {
    "step": { ... },      // Configuration flow steps
    "error": { ... },     // Error messages
    "abort": { ... }      // Abort reasons
  },
  "options": {
    "step": { ... }       // Options flow (for reconfiguration)
  }
}
```

**How It Works**:
- Home Assistant reads this file to display UI text
- Supports multiple languages (currently English only)
- Keys correspond to steps in config_flow.py
- Provides user-friendly error messages

---

### 8. `sensor.py`

**Purpose**: Defines all sensor entities for the integration

**Function: `async_setup_entry()`**
```python
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
```

**What It Does**:
1. Called by Home Assistant to set up sensor platform
2. Retrieves coordinator from `hass.data[DOMAIN][config_entry.entry_id]`
3. Creates instances of all sensor entities with coordinator reference
4. Adds them to Home Assistant

**How It Works**:
- Creates 10 sensor instances passing coordinator to each
- Each sensor is an instance of a specific sensor class
- All sensors added via `async_add_entities()`

**Base Class: `HughesPowerWatchdogSensor`**

```python
class HughesPowerWatchdogSensor(CoordinatorEntity[HughesPowerWatchdogCoordinator], SensorEntity):
    _attr_has_entity_name = True
```

**What It Does**:
- Base class for all sensors
- Inherits from `CoordinatorEntity` for automatic updates
- Sets up common attributes
- Handles unique ID generation
- Implements availability logic
- References device_info from coordinator

**Attributes**:
- `coordinator`: Reference to HughesPowerWatchdogCoordinator
- `_sensor_type`: Type of sensor (voltage, current, etc.)
- `_attr_unique_id`: Unique identifier for entity (based on config_entry.entry_id)
- `_attr_device_info`: DeviceInfo from coordinator (groups entities under one device)

**Properties**:

#### `available`
```python
@property
def available(self) -> bool:
    return self.coordinator.last_update_success and self._sensor_type in self.coordinator.data
```

**What It Does**:
- Returns True if coordinator successfully updated and sensor key exists in data
- Entity becomes unavailable if coordinator fails or data missing
- Handles 30A units (Line 2 sensors unavailable) gracefully

**Sensor Classes**:

#### `HughesPowerWatchdogVoltageSensor`
- **Device Class**: VOLTAGE
- **Unit**: Volts (V)
- **Precision**: 0 decimal places
- **State Class**: MEASUREMENT
- **Instances**: Line 1 Voltage, Line 2 Voltage

#### `HughesPowerWatchdogCurrentSensor`
- **Device Class**: CURRENT
- **Unit**: Amperes (A)
- **Precision**: 1 decimal place
- **State Class**: MEASUREMENT
- **Instances**: Line 1 Current, Line 2 Current

#### `HughesPowerWatchdogPowerSensor`
- **Device Class**: POWER
- **Unit**: Watts (W)
- **Precision**: 0 decimal places
- **State Class**: MEASUREMENT
- **Instances**: Line 1 Power, Line 2 Power, Combined Power

#### `HughesPowerWatchdogEnergySensor`
- **Device Class**: ENERGY
- **Unit**: Kilowatt-hours (kWh)
- **Precision**: 1 decimal place
- **State Class**: TOTAL_INCREASING (cumulative)
- **Instance**: Cumulative Power Usage

#### `HughesPowerWatchdogErrorCodeSensor`
- **Icon**: alert-circle
- **Instance**: Error Code (numeric)

#### `HughesPowerWatchdogErrorTextSensor`
- **Icon**: alert-circle-outline
- **Instance**: Error Description (text)

**Key Sensor Methods**:

Each sensor class now implements:

#### `native_value`
```python
@property
def native_value(self) -> float | int | str | None:
    return self.coordinator.data.get(self._sensor_type)
```

**What It Does**:
- Retrieves current value from coordinator's data dictionary
- Returns None if key doesn't exist (e.g., Line 2 on 30A units)
- Home Assistant automatically calls this when coordinator updates

**How It Works**:
- Each sensor class inherits from `CoordinatorEntity` and base sensor
- Inheriting from `CoordinatorEntity` provides automatic updates when coordinator refreshes
- Sets appropriate device class for proper HA categorization
- Defines units and precision
- State class determines how HA handles the data (measurement vs cumulative)
- Sensors automatically update when coordinator fetches new data (every 30 seconds)
- No manual polling needed - coordinator pattern handles everything

---

### 9. `switch.py`

**Purpose**: Provides switch entity to control BLE monitoring

**Function: `async_setup_entry()`**
```python
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
```

**What It Does**:
1. Retrieves coordinator from `hass.data[DOMAIN][config_entry.entry_id]`
2. Creates monitoring switch entity with coordinator reference
3. Adds it to Home Assistant

**Class: `HughesPowerWatchdogMonitoringSwitch`**

```python
class HughesPowerWatchdogMonitoringSwitch(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], SwitchEntity
):
```

**Attributes**:
- `coordinator`: Reference to HughesPowerWatchdogCoordinator
- `_attr_has_entity_name = True`: Uses device name prefix
- `_attr_icon = "mdi:connection"`: Connection icon
- `_attr_name = "Monitoring"`: Entity name
- `_attr_device_info`: DeviceInfo from coordinator (groups with sensors)

**Properties**:

#### `is_on`
```python
@property
def is_on(self) -> bool:
    return self.coordinator.update_interval is not None
```

**What It Does**:
- Returns True if coordinator's update_interval is set
- Returns False if update_interval is None (paused)

**Methods**:

#### `async_turn_on()`
```python
async def async_turn_on(self, **kwargs: Any) -> None:
```

**What It Does**:
1. Sets coordinator's `update_interval` to 30 seconds
2. Calls `coordinator.async_refresh()` to resume updates
3. Updates switch state in HA
4. Logs monitoring enabled

**How It Works**:
- Restoring update_interval causes coordinator to resume polling
- Next update will use existing connection or establish new one
- Coordinator resumes 30-second polling cycle

#### `async_turn_off()`
```python
async def async_turn_off(self, **kwargs: Any) -> None:
```

**What It Does**:
1. Sets coordinator's `update_interval` to None (pauses polling)
2. Calls `coordinator.async_disconnect()` to disconnect BLE
3. Updates switch state in HA
4. Logs monitoring disabled

**How It Works**:
- Setting update_interval to None stops coordinator polling
- Explicit disconnect cancels background tasks and frees BLE connection
- Switch allows user to disconnect from Hughes device
- Useful when user wants to use Hughes mobile app (device only supports one connection)
- Full cleanup including command queue and health monitor

---

## Configuration Files

### `hacs.json`

**Purpose**: HACS (Home Assistant Community Store) metadata

```json
{
  "name": "Hughes Power Watchdog",
  "render_readme": true,
  "homeassistant": "2023.1.0"
}
```

**How It Works**:
- HACS reads this to understand integration requirements
- `render_readme`: Show README in HACS
- `homeassistant`: Minimum HA version required

---

### `.gitignore`

**Purpose**: Specifies files Git should ignore

**Categories**:
- Python bytecode and build artifacts
- Environment files (.env)
- Database files
- IDE configuration
- OS-specific files
- Testing artifacts
- Home Assistant logs and databases
- Documentation files (how-it-works.md)

**How It Works**:
- Prevents sensitive data (like .env) from being committed
- Keeps repository clean of build artifacts
- Excludes user-specific IDE settings
- Excludes development documentation from commits

---

### `.env.example`

**Purpose**: Template for environment variables

**Current State**:
- Placeholder only
- Integration uses UI configuration, not environment variables
- Reserved for future use (API keys, etc.)

---

### `config.yaml.example`

**Purpose**: Configuration guidance

**Current State**:
- Documents that YAML configuration is not supported
- Explains UI-based configuration process
- Notes optional scan_interval setting

---

## Documentation Files

### `README.md`

**Purpose**: User-facing documentation

**Sections**:
- Features and supported models
- Installation instructions (HACS and manual)
- Configuration steps
- Requirements
- Troubleshooting
- Credits and license

**How It Works**:
- Displayed on GitHub repository
- Rendered in HACS
- Provides complete user guide

---

### `CLAUDE.md`

**Purpose**: Development guidelines for AI assistant

**Sections**:
- Planning workflow
- Development process
- Code standards
- Git workflow
- Project-specific instructions
- Documentation maintenance requirements

**How It Works**:
- Guides development process
- Ensures consistency
- Documents project conventions

---

### `tasks/` Directory

**Purpose**: Task tracking and project planning

**Files**:
- `todo.md`: Original task tracking
- `ha-guidelines-compliance.md`: HA guidelines review
- `persistent-connection-refactor.md`: v0.3.0 refactor plan
- `coordinator-implementation.md`: v0.2.0 implementation plan

**How It Works**:
- Tracks implementation progress
- Documents completed work
- Plans future development
- Records architectural decisions

---

## Data Flow (v0.3.0 Persistent Connection Architecture)

### 1. Discovery
```
Home Assistant Bluetooth → manifest.json patterns (PMD*/PWS*) → config_flow.async_step_bluetooth()
```
- HA's bluetooth component detects devices with names starting with "PMD" or "PWS"
- Integration automatically offered to user
- User can also manually add via UI

### 2. Configuration
```
User confirms device → Config entry created → __init__.async_setup_entry()
```
- MAC address stored in config entry
- Device name stored as entry title

### 3. Coordinator Initialization
```
__init__.async_setup_entry() → Create HughesPowerWatchdogCoordinator
→ Start background tasks → async_config_entry_first_refresh()
```
- Coordinator created with config_entry reference
- Background tasks started (command worker, health monitor)
- Initial data fetch performed
- Persistent connection established
- Coordinator stored in hass.data[DOMAIN][entry_id]

### 4. Platform Setup
```
async_setup_entry() → sensor.py setup → switch.py setup → Entities created with coordinator reference
```
- 10 sensor entities created
- 1 switch entity created
- All entities inherit from CoordinatorEntity
- All entities reference device_info from coordinator
- Entities automatically subscribe to coordinator updates

### 5. Data Updates (Every 30 seconds)
```
Coordinator timer → _async_update_data() → Check command queue
→ If empty: _request_device_status() → _ensure_connected()
→ Check existing connection → start_notify(TX_CHAR) → _notification_handler()
→ Receive 2x 20-byte chunks → _parse_data_packet() → _build_data_dict()
→ stop_notify() → Update last_activity_time → Return data dict → Entities auto-update
```

**Detailed Flow (v0.3.0)**:
1. Coordinator timer triggers every 30 seconds
2. `_async_update_data()` checks if commands are in queue
3. If commands pending, return cached data (yield to commands)
4. Otherwise, call `_request_device_status()`
5. `_ensure_connected()` checks for existing connection
6. If connected and not idle, reuse connection (no reconnection overhead)
7. If not connected, get BLEDevice from HA's bluetooth component
8. Create BleakClient and connect with retry logic
9. Subscribe to TX characteristic for notifications
10. Device sends Chunk 1 (20 bytes): Header + voltage/current/power/energy/error
11. Device sends Chunk 2 (20 bytes): Line identifier
12. Notification handler buffers chunks
13. After 40 bytes received, parses complete packet
14. Extracts values using struct.unpack for big-endian int32
15. Identifies Line 1 or Line 2 from bytes 37-39
16. Builds data dictionary with all sensor values
17. Unsubscribes from notifications (connection stays open)
18. Updates `_last_activity_time` to current timestamp
19. Returns data to coordinator
20. Coordinator marks update successful
21. All entities receive notification and call native_value property
22. HA updates entity states in dashboard

**Connection Lifecycle**:
- First poll: Establishes connection
- Subsequent polls (within 120s): Reuse existing connection
- After 120s idle: Health monitor disconnects
- Next poll: Re-establishes connection

### 6. Connection Health Monitoring
```
Health monitor task (every 30s) → Check last_activity_time
→ If idle > 120s: _disconnect() → Free BLE connection slot
```

**Health Monitor Flow**:
1. Background task runs continuously
2. Every 30 seconds, checks idle time
3. Calculates: `current_time - last_activity_time`
4. If idle > 120 seconds, calls `_disconnect()`
5. Logs disconnect reason
6. Connection freed for other apps/integrations
7. Next poll will re-establish connection

### 7. Command Execution (Future Two-Way Communication)
```
Entity calls execute_command() → Queue command with future
→ Command worker picks up command → _ensure_connected()
→ Execute command function → _request_device_status()
→ Set future result → Entities auto-update with new state
```

**Command Flow (Ready for Implementation)**:
1. Entity/service calls `coordinator.execute_command(command_func)`
2. Command queued with asyncio.Future
3. Command worker (background task) picks up command
4. Worker ensures connection is active
5. Worker calls command function with BleakClient
6. Command writes to RX characteristic
7. Worker immediately requests device status
8. New state received and propagated to entities
9. UI updates reflect command result
10. Future resolved with result

**Command Queue Benefits**:
- Prevents concurrent BLE operations
- Ensures device sees one command at a time
- Provides responsive UI feedback
- Ready for future device control features

### 8. Monitoring Control
```
User toggles switch → switch.is_on property → switch.async_turn_on/off()
→ Set coordinator.update_interval (30s or None) → coordinator.async_disconnect()
→ Coordinator pauses/resumes polling → Background tasks canceled/started
```

**Turn Off Flow**:
1. User toggles switch to OFF
2. Switch sets coordinator.update_interval = None
3. Switch calls coordinator.async_disconnect()
4. Background tasks canceled (command worker, health monitor)
5. BLE connection closed
6. Coordinator stops polling
7. Sensors retain last values but marked as unavailable

**Turn On Flow**:
1. User toggles switch to ON
2. Switch sets coordinator.update_interval = 30 seconds
3. Background tasks restarted
4. Switch calls coordinator.async_refresh()
5. Coordinator immediately fetches new data
6. Connection established
7. Normal 30-second polling resumes

---

## Implementation Status

### ✅ Completed (v0.3.0)

1. **Persistent BLE Connection**
   - ✅ Persistent connection with 120-second idle timeout
   - ✅ Connection health monitoring background task
   - ✅ Automatic reconnection on connection loss
   - ✅ Adaptive retry with exponential backoff
   - ✅ Connection reuse across polling cycles
   - ✅ Thread-safe connection management with asyncio.Lock

2. **Command Queue System**
   - ✅ Command queue infrastructure (asyncio.Queue)
   - ✅ Command worker background task
   - ✅ Sequential command execution
   - ✅ Command/polling priority (commands take precedence)
   - ✅ Public execute_command() API
   - ✅ Status verification after commands
   - ✅ Ready for future two-way communication

3. **Dependency Optimization**
   - ✅ Removed bleak-retry-connector dependency
   - ✅ Custom retry logic implementation
   - ✅ Uses only HA's built-in bluetooth component
   - ✅ Follows HA best practices (minimal dependencies)
   - ✅ Direct BleakClient usage

4. **Device Registry Integration**
   - ✅ device_info property in coordinator
   - ✅ All entities grouped under single device
   - ✅ Proper manufacturer and model info
   - ✅ Bluetooth connection tracking

5. **BLE Communication**
   - ✅ Service and characteristic UUIDs identified from ESPHome source
   - ✅ Data packet structure documented (40 bytes in two 20-byte chunks)
   - ✅ Data parsing logic implemented
   - ✅ Connection management with proxy support
   - ✅ BLE notification handler created

6. **Data Coordinator**
   - ✅ Coordinator class for centralized BLE communication
   - ✅ 30-second polling mechanism
   - ✅ State updates to all entities
   - ✅ Proxy-compatible using HA's bluetooth component

7. **Error Handling**
   - ✅ BLE connection errors handled via UpdateFailed
   - ✅ Custom retry logic with exponential backoff
   - ✅ Device disconnection managed
   - ✅ Entity availability based on coordinator success
   - ✅ Background task error handling

8. **Switch Functionality**
   - ✅ Turn on/off controls coordinator polling
   - ✅ Actually connects/disconnects BLE
   - ✅ Cancels/restarts background tasks
   - ✅ Frees connection slots when disabled

9. **Sensor Updates**
   - ✅ All sensors inherit from CoordinatorEntity
   - ✅ Automatic updates when coordinator refreshes
   - ✅ Proper availability handling
   - ✅ 30A vs 50A device support

10. **Home Assistant Guidelines Compliance**
    - ✅ Logging uses % formatting (not f-strings)
    - ✅ All functions have type hints
    - ✅ All classes and functions have docstrings
    - ✅ has_entity_name = True for all entities
    - ✅ Unique IDs based on config_entry.entry_id
    - ✅ should_poll = False (CoordinatorEntity)
    - ✅ available property implemented
    - ✅ device_info for device registry
    - ✅ Import ordering (stdlib, third-party, HA, local)
    - ✅ Async/await patterns throughout

### ❌ Not Yet Implemented

1. **Two-Way Communication**
   - ❌ Command implementations (infrastructure ready)
   - ❌ Write to RX characteristic
   - ❌ Command validation
   - ❌ Command error handling
   - ❌ Device control services

2. **Advanced Features**
   - ❌ Configurable scan interval via options flow
   - ❌ Configurable idle timeout
   - ❌ Statistics/history for power usage
   - ❌ Alerts/notifications for error conditions
   - ❌ Firmware version extraction
   - ❌ Serial number extraction

3. **Testing**
   - ❌ Not tested with actual hardware
   - ❌ Unknown if data parsing is 100% correct
   - ❌ May need adjustments based on real device behavior
   - ❌ Persistent connection behavior with real device
   - ❌ Command queue behavior verification

---

## Version History

### v0.3.2 (Current)
- Fixed BLE connection warning by using `establish_connection()` from bleak-retry-connector
- Changed invalid header logging from `warning` to `debug` level (device sends multiple packet types)
- Cleaner logs - non-data packets are silently skipped instead of flooding warnings

### v0.3.1
- Fix BLE connection and device registry issues

### v0.3.0
- **Major Architectural Change**: Persistent Connection Pattern
- **Command Queue System**: Infrastructure for future two-way communication
- Removed bleak-retry-connector dependency
- Implemented custom retry logic with exponential backoff
- Added connection health monitoring (120-second idle timeout)
- Added command worker background task
- Added command queue with execute_command() API
- Connection reuse across polling cycles
- Adaptive delay system (exponential backoff on failure, 25% reduction on success)
- Thread-safe connection management with asyncio.Lock
- Polling yields to command queue (commands have priority)
- Background tasks properly managed (started/stopped with coordinator)
- Uses only HA's built-in bluetooth component
- Follows HA development guidelines completely
- Ready for future device control commands
- Syntax-checked and ready for testing

### v0.2.0
- **Major Feature**: BLE Coordinator Implementation
- Created `coordinator.py` with full BLE communication
- Proxy-compatible using `bleak-retry-connector`
- Automatic connection/retry logic for ESP32 proxies
- Data parsing for 40-byte packets
- Line 1/Line 2 identification
- Error code mapping
- 30-second polling interval
- Updated all entities to use `CoordinatorEntity`
- Sensors now display real data from coordinator
- Switch controls coordinator polling (pause/resume)
- Full connection lifecycle management
- Proper entity availability handling
- Device registry integration (device_info)
- HA guidelines compliance review and fixes
- Syntax-checked and ready for testing

### v0.1.0
- Initial HACS-compatible structure
- UI-based configuration flow
- Entity definitions (sensors and switch)
- Documentation complete
- BLE UUIDs and data protocol identified from ESPHome source
- Data packet structure fully documented
- Placeholder implementations (no actual BLE communication)

---

## Next Development Steps

### Phase 1: Hardware Testing ⏭️ NEXT
1. Test with actual Hughes Power Watchdog device
   - Verify BLE discovery works
   - Confirm data packet parsing is correct
   - Validate voltage/current/power readings
   - Test 30A and 50A unit differences
   - Check error code detection
   - Verify persistent connection behavior
   - Test idle timeout (120 seconds)
   - Verify connection reuse across polls
   - Test command queue infrastructure

2. Bug fixes based on testing
   - Adjust data parsing if needed
   - Fix any connection issues
   - Handle edge cases discovered
   - Tune idle timeout if needed
   - Adjust retry delays if needed

### Phase 2: Two-Way Communication
3. Reverse engineer command protocol
   - Analyze RX characteristic writes
   - Document command format
   - Identify available commands
   - Understand command responses

4. Implement device control
   - Use existing command queue system
   - Add service definitions
   - Implement command functions
   - Add error handling for commands
   - Test command execution
   - Verify status updates after commands

### Phase 3: Enhanced Features
5. Add device information
   - Extract model number from device
   - Track firmware version if available
   - Show device serial number
   - Enhanced device registry entry

6. Configuration options
   - Configurable scan interval via options flow
   - Configurable idle timeout
   - Allow users to adjust polling frequency
   - Add option to disable Line 2 sensors on 30A units

7. Diagnostics and debugging
   - Add diagnostic sensors (RSSI, connection status)
   - Improve logging for troubleshooting
   - Add config flow diagnostics
   - Connection state monitoring

### Phase 4: Advanced Features
8. Notifications and automations
   - Alert on error conditions
   - Notify when voltage/current out of range
   - Integration with HA's notification system

9. Statistics and history
   - Track historical power usage
   - Daily/weekly/monthly energy reports
   - Integration with Energy Dashboard

### Completed ✅
- ~~Analyze Hughes device BLE protocol~~ (v0.1.0)
- ~~Create BLE coordinator~~ (v0.2.0)
- ~~Implement data updates~~ (v0.2.0)
- ~~Implement switch functionality~~ (v0.2.0)
- ~~Add error handling and recovery~~ (v0.2.0)
- ~~Handle 30A vs 50A devices~~ (v0.2.0)
- ~~Review HA development guidelines~~ (v0.2.0)
- ~~Add device_info for device registry~~ (v0.2.0)
- ~~Refactor to persistent connection pattern~~ (v0.3.0)
- ~~Add command queue infrastructure~~ (v0.3.0)
- ~~Remove external dependencies~~ (v0.3.0)
- ~~Implement connection health monitoring~~ (v0.3.0)
- ~~Add adaptive retry logic~~ (v0.3.0)

---

**Document Version**: 0.3.0
**Last Updated**: 2026-01-23
**Status**: Persistent connection architecture implemented, command queue ready for two-way communication, awaiting hardware testing
