"""Constants for the Hughes Power Watchdog integration."""

from homeassistant.const import Platform

DOMAIN = "hughes_power_watchdog"
NAME = "Hughes Power Watchdog"

# Platforms
PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.LIGHT, Platform.SENSOR, Platform.SWITCH, Platform.TODO]

# Configuration
CONF_MAC_ADDRESS = "mac_address"

# Device name prefixes that we look for
# V1 devices: PMD, PWS, PMS (use V1/legacy protocol)
# V2 devices: WD_V5 / WD_E5 / WD_V6 / WD_E6 (use V2 protocol)
DEVICE_NAME_PREFIXES = ["PMD", "PWS", "PMS", "WD_V5", "WD_E5", "WD_V6", "WD_E6"]
DEVICE_NAME_PREFIXES_V1 = ["PMD", "PWS", "PMS"]
DEVICE_NAME_PREFIXES_V2 = ["WD_V5", "WD_E5", "WD_V6", "WD_E6"]

# Connection health check interval (coordinator watchdog, not data polling)
# Actual data arrives via push notifications from the device (~1s intervals)
CONNECTION_CHECK_INTERVAL = 30  # seconds

# Connection management
NOTIFICATION_STALE_TIMEOUT = 60  # seconds - warn/reconnect if no notifications
CONNECTION_MAX_ATTEMPTS = 3  # Maximum connection retry attempts
CONNECTION_MAX_DELAY = 6.0  # Maximum retry delay in seconds
CONNECTION_DELAY_REDUCTION = 0.75  # Multiply delay by this on success
DATA_COLLECTION_TIMEOUT = 3  # seconds - wait for device to send data chunks

# =============================================================================
# V1 PROTOCOL (PMD/PWS/PMS devices)
# =============================================================================
# BLE Service and Characteristic UUIDs (from ESPHome implementation)
# Source: https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog
V1_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
V1_CHARACTERISTIC_UUID_TX = "0000ffe2-0000-1000-8000-00805f9b34fb"  # Device transmits data
V1_CHARACTERISTIC_UUID_RX = "0000fff5-0000-1000-8000-00805f9b34fb"  # General write (unused)
V1_CHARACTERISTIC_UUID_CMD = "00001003-0000-1000-8000-00805f9b34fb"  # Device receives commands

# Backward-compatible aliases
LEGACY_SERVICE_UUID = V1_SERVICE_UUID
CHARACTERISTIC_UUID_TX = V1_CHARACTERISTIC_UUID_TX

# =============================================================================
# V2 PROTOCOL (WD_V5_* / WD_E5_* / WD_V6_* / WD_E6_* devices)
# =============================================================================
# Reverse engineered from Bluetooth captures and Android app source - see docs/protocol.md
V2_SERVICE_UUID = "000000ff-0000-1000-8000-00805f9b34fb"
V2_CHARACTERISTIC_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"  # Bidirectional

# V2 Protocol framing
V2_HEADER = b"$yw@"  # 0x24797740
V2_END_MARKER = b"q!"  # 0x7121
V2_INIT_COMMAND = b"!%!%,protocol,open,"

# V2 Protocol framing constants
V2_PROTOCOL_VERSION = 0x01
V2_SEQUENCE_MAX = 100

# V2 Message types / Command IDs (byte 6 in packet)
V2_MSG_TYPE_DATA = 0x01  # DLReport - Live sensor data
V2_MSG_TYPE_ERROR = 0x02  # ErrorReport - Historical error logs
V2_CMD_ENERGY_RESET = 0x03  # EnergyReset - Reset kWh counter
V2_CMD_ERROR_DEL = 0x05  # ErrorDel - Delete error log(s)
V2_CMD_SET_TIME = 0x06  # SetTime - Sync device clock
V2_MSG_TYPE_CONTROL = 0x06  # Alias for backward compat
V2_CMD_SET_BACKLIGHT = 0x07  # SetBacklight - LED brightness (0-5)
V2_CMD_SET_INIT_DATA = 0x0A  # SetInitData - Initialization handshake
V2_CMD_SET_OPEN = 0x0B  # SetOpen - Toggle main power relay
V2_CMD_NEUTRAL_DETECTION = 0x0D  # NeutralDetection - Enable/disable ground monitoring

# V2 ResultRes acknowledgment
V2_RESULT_SUCCESS = 0x01

# V2 SetOpen payload values
V2_RELAY_ON = 0x01
V2_RELAY_OFF = 0x02

# V2 NeutralDetection payload values
V2_NEUTRAL_ENABLE = 0x00
V2_NEUTRAL_DISABLE = 0x01

# V2 Backlight range
V2_BACKLIGHT_MAX = 5

# V2 Data packet byte positions
# Header fields
V2_BYTE_HEADER_START = 0
V2_BYTE_HEADER_END = 4
V2_BYTE_VERSION = 4
V2_BYTE_SEQUENCE = 5
V2_BYTE_MSG_TYPE = 6
V2_BYTE_DATA_LEN_START = 7
V2_BYTE_DATA_LEN_END = 9

# Line 1 data (payload starts at byte 9)
V2_BYTE_VOLTAGE_START = 9
V2_BYTE_VOLTAGE_END = 13
V2_BYTE_CURRENT_START = 13
V2_BYTE_CURRENT_END = 17
V2_BYTE_POWER_START = 17
V2_BYTE_POWER_END = 21
V2_BYTE_ENERGY_START = 21
V2_BYTE_ENERGY_END = 25

# Single-block extended fields (bytes 25-42)
V2_BYTE_TEMP1_START = 25  # Internal/unknown
V2_BYTE_TEMP1_END = 29
V2_BYTE_OUTPUT_VOLTAGE_START = 29
V2_BYTE_OUTPUT_VOLTAGE_END = 33
V2_BYTE_BACKLIGHT = 33
V2_BYTE_NEUTRAL_DETECTION = 34
V2_BYTE_BOOST_MODE = 35
V2_BYTE_TEMPERATURE = 36
V2_BYTE_FREQUENCY_START = 37
V2_BYTE_FREQUENCY_END = 41
V2_BYTE_ERROR_CODE = 41
V2_BYTE_RELAY_STATUS = 42

# V2 minimum packet sizes
V2_MIN_DATA_PACKET_SIZE = 21  # Minimum for L1 V/I/P extraction
V2_MIN_ENERGY_PACKET_SIZE = 25  # Minimum for L1 V/I/P/E extraction
V2_MIN_EXTENDED_PACKET_SIZE = 43  # Minimum for all single-block fields
V2_FULL_DATA_PACKET_SIZE = 45  # Full single-block packet with end marker

# V2 dual-block layout (50A devices, 79-byte packets)
# Block 2 (Line 2) starts at byte 43, same field layout as Block 1
V2_DUAL_BLOCK_L2_VOLTAGE_START = 43
V2_DUAL_BLOCK_L2_VOLTAGE_END = 47
V2_DUAL_BLOCK_L2_CURRENT_START = 47
V2_DUAL_BLOCK_L2_CURRENT_END = 51
V2_DUAL_BLOCK_L2_POWER_START = 51
V2_DUAL_BLOCK_L2_POWER_END = 55
V2_DUAL_BLOCK_L2_ENERGY_START = 55
V2_DUAL_BLOCK_L2_ENERGY_END = 59
# Block 2 extended fields (bytes 59-76)
V2_DUAL_BLOCK_L2_TEMP1_START = 59
V2_DUAL_BLOCK_L2_TEMP1_END = 63
V2_DUAL_BLOCK_L2_OUTPUT_VOLTAGE_START = 63
V2_DUAL_BLOCK_L2_OUTPUT_VOLTAGE_END = 67
V2_DUAL_BLOCK_L2_BACKLIGHT = 67
V2_DUAL_BLOCK_L2_NEUTRAL_DETECTION = 68
V2_DUAL_BLOCK_L2_BOOST_MODE = 69
V2_DUAL_BLOCK_L2_TEMPERATURE = 70
V2_DUAL_BLOCK_L2_FREQUENCY_START = 71
V2_DUAL_BLOCK_L2_FREQUENCY_END = 75
V2_DUAL_BLOCK_L2_ERROR_CODE = 75
V2_DUAL_BLOCK_L2_RELAY_STATUS = 76

# Voltage validation range (for detecting valid Line 2 data)
V2_VOLTAGE_MIN = 90.0  # Minimum reasonable voltage (V)
V2_VOLTAGE_MAX = 145.0  # Maximum reasonable voltage (V)

# V1 frequency field in chunk 2 (bytes 31-34)
V1_BYTE_FREQUENCY_START = 31
V1_BYTE_FREQUENCY_END = 35
# Frequency conversion factor (int32 / 100 = Hz)
FREQUENCY_CONVERSION_FACTOR = 100

# V1 Commands (ASCII strings sent via RX characteristic)
V1_CMD_RELAY_ON = "relayOn"
V1_CMD_ENERGY_RESET = "reset"
V1_CMD_DELETE_ALL_RECORDS = "deleteAllRecord"
V1_CMD_SET_TIME = "setTime"
V1_CMD_BACKLIGHT = "backLight"

# V1 Backlight range
V1_BACKLIGHT_MAX = 4

# Legacy Data Protocol Constants
# Device sends 40 bytes total in two 20-byte chunks
CHUNK_SIZE = 20
TOTAL_DATA_SIZE = 40
HEADER_BYTES = b"\x01\x03\x20"

# Byte positions in data chunks
# Chunk 1 (bytes 0-19):
BYTE_HEADER_START = 0
BYTE_HEADER_END = 3
BYTE_VOLTAGE_START = 3
BYTE_VOLTAGE_END = 7
BYTE_CURRENT_START = 7
BYTE_CURRENT_END = 11
BYTE_POWER_START = 11
BYTE_POWER_END = 15
BYTE_ENERGY_START = 15
BYTE_ENERGY_END = 19
BYTE_ERROR_CODE = 19

# Chunk 2 (bytes 20-39):
BYTE_LINE_ID_START = 37
BYTE_LINE_ID_END = 40

# Line identifiers (bytes 37-39)
LINE_1_ID = b"\x00\x00\x00"
LINE_2_ID = b"\x01\x01\x01"

# Data conversion factor (big-endian int32 divided by this value)
DATA_CONVERSION_FACTOR = 10000

# Sensor keys
SENSOR_VOLTAGE_L1 = "voltage_line_1"
SENSOR_CURRENT_L1 = "current_line_1"
SENSOR_POWER_L1 = "power_line_1"
SENSOR_VOLTAGE_L2 = "voltage_line_2"
SENSOR_CURRENT_L2 = "current_line_2"
SENSOR_POWER_L2 = "power_line_2"
SENSOR_COMBINED_POWER = "combined_power"
SENSOR_TOTAL_POWER = "total_power"
SENSOR_ERROR_CODE = "error_code"
SENSOR_ERROR_TEXT = "error_text"
SENSOR_FREQUENCY = "frequency"
SENSOR_FREQUENCY_L2 = "frequency_line_2"
SENSOR_OUTPUT_VOLTAGE = "output_voltage"
SENSOR_TEMPERATURE = "temperature"
SENSOR_RELAY_STATUS = "relay_status"
SENSOR_BOOST_MODE = "boost_mode"
SENSOR_NEUTRAL_DETECTION = "neutral_detection"

# Switch keys
SWITCH_MONITORING = "monitoring"
SWITCH_RELAY = "relay"
SWITCH_NEUTRAL_DETECTION_CONTROL = "neutral_detection_control"

# Button keys
BUTTON_ENERGY_RESET = "energy_reset"
BUTTON_ERROR_DELETE = "error_delete"

# Light keys
LIGHT_BACKLIGHT = "backlight"

# Sensor key for backlight current level (read from V2 data stream byte 33)
SENSOR_BACKLIGHT = "backlight"

# Error code mapping (from Hughes Power Watchdog official documentation and app source)
# Source: PWD-3050EPO Installation & Operating Instructions manual, V1/V2 app source
ERROR_CODES = {
    0: "No Error",
    1: "Line 1 voltage exceeded 132V or dropped below 104V",
    2: "Line 2 voltage exceeded 132V or dropped below 104V",
    3: "Line 1 amperage rating exceeded",
    4: "Line 2 amperage rating exceeded",
    5: "Line 1 hot and neutral wires reversed",
    6: "Line 2 hot and neutral wires reversed",
    7: "Ground connection lost",
    8: "No neutral circuit detected",
    9: "Surge protection capacity depleted - replace surge board",
    11: "Frequency error (F1)",
    12: "Frequency error (F2)",
}
