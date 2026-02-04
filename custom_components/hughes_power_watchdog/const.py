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
# V5 devices: WD_V5 (use new protocol)
DEVICE_NAME_PREFIXES = ["PMD", "PWS", "PMS", "WD_V5"]
DEVICE_NAME_PREFIXES_LEGACY = ["PMD", "PWS", "PMS"]
DEVICE_NAME_PREFIXES_V5 = ["WD_V5"]

# Update interval
DEFAULT_SCAN_INTERVAL = 30  # seconds

# Connection management
CONNECTION_IDLE_TIMEOUT = 120  # seconds - disconnect after this much idle time
CONNECTION_MAX_ATTEMPTS = 3  # Maximum connection retry attempts
CONNECTION_MAX_DELAY = 6.0  # Maximum retry delay in seconds
CONNECTION_DELAY_REDUCTION = 0.75  # Multiply delay by this on success
DATA_COLLECTION_TIMEOUT = 3  # seconds - wait for device to send data chunks

# =============================================================================
# LEGACY PROTOCOL (PMD/PWS/PMS devices)
# =============================================================================
# BLE Service and Characteristic UUIDs (from ESPHome implementation)
# Source: https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID_TX = "0000ffe2-0000-1000-8000-00805f9b34fb"  # Device transmits data
CHARACTERISTIC_UUID_RX = "0000fff5-0000-1000-8000-00805f9b34fb"  # Device receives commands

# =============================================================================
# WD_V5 PROTOCOL (WD_V5_* devices)
# =============================================================================
# Reverse engineered from Bluetooth captures - see bt_logs/WD_V5_PROTOCOL.md
WD_V5_SERVICE_UUID = "000000ff-0000-1000-8000-00805f9b34fb"
WD_V5_CHARACTERISTIC_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"  # Bidirectional

# WD_V5 Protocol framing
WD_V5_HEADER = b"$yw@"  # 0x24797740
WD_V5_END_MARKER = b"q!"  # 0x7121
WD_V5_INIT_COMMAND = b"!%!%,protocol,open,"

# WD_V5 Message types (byte 6 in packet)
WD_V5_MSG_TYPE_DATA = 0x01  # Power data packet
WD_V5_MSG_TYPE_STATUS = 0x02  # Status/info packet
WD_V5_MSG_TYPE_CONTROL = 0x06  # Control/ack packet

# WD_V5 Data packet byte positions (45-byte data packet)
WD_V5_BYTE_HEADER_START = 0
WD_V5_BYTE_HEADER_END = 4
WD_V5_BYTE_SEQUENCE = 5
WD_V5_BYTE_MSG_TYPE = 6
WD_V5_BYTE_VOLTAGE_START = 9
WD_V5_BYTE_VOLTAGE_END = 13
WD_V5_BYTE_CURRENT_START = 13
WD_V5_BYTE_CURRENT_END = 17
WD_V5_BYTE_POWER_START = 17
WD_V5_BYTE_POWER_END = 21
WD_V5_BYTE_ENERGY_START = 21
WD_V5_BYTE_ENERGY_END = 25

# WD_V5 minimum packet sizes
WD_V5_MIN_DATA_PACKET_SIZE = 21  # Minimum for V/I/P extraction
WD_V5_MIN_ENERGY_PACKET_SIZE = 25  # Minimum for V/I/P/E extraction
WD_V5_FULL_DATA_PACKET_SIZE = 45  # Full packet with all fields

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
