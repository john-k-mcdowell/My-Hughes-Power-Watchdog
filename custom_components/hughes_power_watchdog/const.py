"""Constants for the Hughes Power Watchdog integration."""

from homeassistant.const import Platform

DOMAIN = "hughes_power_watchdog"
NAME = "Hughes Power Watchdog"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

# Configuration
CONF_MAC_ADDRESS = "mac_address"

# Device name prefixes that we look for
DEVICE_NAME_PREFIXES = ["PMD", "PWS", "PMS", "WD"]

# Update interval
DEFAULT_SCAN_INTERVAL = 30  # seconds

# Connection management
CONNECTION_IDLE_TIMEOUT = 120  # seconds - disconnect after this much idle time
CONNECTION_MAX_ATTEMPTS = 3  # Maximum connection retry attempts
CONNECTION_MAX_DELAY = 6.0  # Maximum retry delay in seconds
CONNECTION_DELAY_REDUCTION = 0.75  # Multiply delay by this on success
DATA_COLLECTION_TIMEOUT = 3  # seconds - wait for device to send data chunks

# BLE Service and Characteristic UUIDs (from ESPHome implementation)
# Source: https://github.com/spbrogan/esphome/tree/PolledSensor/esphome/components/hughes_power_watchdog
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID_TX = "0000ffe2-0000-1000-8000-00805f9b34fb"  # Device transmits data
CHARACTERISTIC_UUID_RX = "0000fff5-0000-1000-8000-00805f9b34fb"  # Device receives commands

# Data Protocol Constants
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
