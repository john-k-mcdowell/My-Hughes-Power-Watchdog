"""Constants for the Hughes Power Watchdog integration."""

from homeassistant.const import Platform

DOMAIN = "hughes_power_watchdog"
NAME = "Hughes Power Watchdog"

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

# Configuration
CONF_MAC_ADDRESS = "mac_address"

# Device names that we look for
DEVICE_NAME_PMD = "PMD"
DEVICE_NAME_PWS = "PWS"

# Update interval
DEFAULT_SCAN_INTERVAL = 30  # seconds

# BLE Service and Characteristic UUIDs (to be determined from device analysis)
# These will need to be updated based on actual device communication
SERVICE_UUID = "00000000-0000-0000-0000-000000000000"  # Placeholder
CHARACTERISTIC_UUID = "00000000-0000-0000-0000-000000000000"  # Placeholder

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
