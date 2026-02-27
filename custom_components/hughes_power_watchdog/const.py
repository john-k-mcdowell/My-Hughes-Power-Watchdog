"""Constants for the Hughes Power Watchdog integration."""

from homeassistant.const import Platform

DOMAIN = "hughes_power_watchdog"
NAME = "Hughes Power Watchdog"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

# Configuration
CONF_MAC_ADDRESS = "mac_address"

# Device name prefixes that we look for
# Legacy devices: PMD, PWS, PMS (use old protocol)
# Modern V5 devices: WD_V5 / WD_E5 (use new protocol)
DEVICE_NAME_PREFIXES = ["PMD", "PWS", "PMS", "WD_V5", "WD_E5"]
DEVICE_NAME_PREFIXES_LEGACY = ["PMD", "PWS", "PMS"]
DEVICE_NAME_PREFIXES_MODERN_V5 = ["WD_V5", "WD_E5"]

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
# LEGACY PROTOCOL (PMD/PWS/PMS devices)
# =============================================================================
# BLE Service and Characteristic UUIDs (from ESPHome implementation)
# Source: https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog
LEGACY_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
LEGACY_CHARACTERISTIC_UUID_TX = "0000ffe2-0000-1000-8000-00805f9b34fb"  # Device transmits data
LEGACY_CHARACTERISTIC_UUID_RX = "0000fff5-0000-1000-8000-00805f9b34fb"  # Device receives commands

# Backward-compatible aliases
SERVICE_UUID = LEGACY_SERVICE_UUID
CHARACTERISTIC_UUID_TX = LEGACY_CHARACTERISTIC_UUID_TX
CHARACTERISTIC_UUID_RX = LEGACY_CHARACTERISTIC_UUID_RX

# =============================================================================
# MODERN V5 PROTOCOL (WD_V5_* / WD_E5_* devices)
# =============================================================================
# Reverse engineered from Bluetooth captures - see docs/protocol.md
MODERN_V5_SERVICE_UUID = "000000ff-0000-1000-8000-00805f9b34fb"
MODERN_V5_CHARACTERISTIC_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"  # Bidirectional

# Modern V5 Protocol framing
MODERN_V5_HEADER = b"$yw@"  # 0x24797740
MODERN_V5_END_MARKER = b"q!"  # 0x7121
MODERN_V5_INIT_COMMAND = b"!%!%,protocol,open,"

# Modern V5 Message types (byte 6 in packet)
MODERN_V5_MSG_TYPE_DATA = 0x01  # Power data packet
MODERN_V5_MSG_TYPE_STATUS = 0x02  # Status/info packet
MODERN_V5_MSG_TYPE_CONTROL = 0x06  # Control/ack packet

# Modern V5 Data packet byte positions (45-byte data packet)
# Line 1 data
MODERN_V5_BYTE_HEADER_START = 0
MODERN_V5_BYTE_HEADER_END = 4
MODERN_V5_BYTE_SEQUENCE = 5
MODERN_V5_BYTE_MSG_TYPE = 6
MODERN_V5_BYTE_VOLTAGE_START = 9
MODERN_V5_BYTE_VOLTAGE_END = 13
MODERN_V5_BYTE_CURRENT_START = 13
MODERN_V5_BYTE_CURRENT_END = 17
MODERN_V5_BYTE_POWER_START = 17
MODERN_V5_BYTE_POWER_END = 21
MODERN_V5_BYTE_ENERGY_START = 21
MODERN_V5_BYTE_ENERGY_END = 25

# Line 2 data (speculative - for dual-phase V5 devices if they exist)
# Assuming same format as Line 1, starting at byte 25
MODERN_V5_BYTE_L2_VOLTAGE_START = 25
MODERN_V5_BYTE_L2_VOLTAGE_END = 29
MODERN_V5_BYTE_L2_CURRENT_START = 29
MODERN_V5_BYTE_L2_CURRENT_END = 33
MODERN_V5_BYTE_L2_POWER_START = 33
MODERN_V5_BYTE_L2_POWER_END = 37

# Modern V5 minimum packet sizes
MODERN_V5_MIN_DATA_PACKET_SIZE = 21  # Minimum for L1 V/I/P extraction
MODERN_V5_MIN_ENERGY_PACKET_SIZE = 25  # Minimum for L1 V/I/P/E extraction
MODERN_V5_MIN_L2_PACKET_SIZE = 37  # Minimum for L2 V/I/P extraction (speculative)
MODERN_V5_FULL_DATA_PACKET_SIZE = 45  # Full packet with all fields

# Voltage validation range (for detecting valid Line 2 data)
MODERN_V5_VOLTAGE_MIN = 90.0  # Minimum reasonable voltage (V)
MODERN_V5_VOLTAGE_MAX = 145.0  # Maximum reasonable voltage (V)

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

# Switch keys
SWITCH_MONITORING = "monitoring"

# Error code mapping (from Hughes Power Watchdog official documentation)
# Source: PWD-3050EPO Installation & Operating Instructions manual
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
}
