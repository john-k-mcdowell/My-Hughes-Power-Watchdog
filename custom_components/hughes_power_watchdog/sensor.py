"""Sensor platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SENSOR_COMBINED_POWER,
    SENSOR_CURRENT_L1,
    SENSOR_CURRENT_L2,
    SENSOR_ERROR_CODE,
    SENSOR_ERROR_TEXT,
    SENSOR_POWER_L1,
    SENSOR_POWER_L2,
    SENSOR_TOTAL_POWER,
    SENSOR_VOLTAGE_L1,
    SENSOR_VOLTAGE_L2,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog sensors."""
    sensors = [
        HughesPowerWatchdogVoltageSensor(config_entry, SENSOR_VOLTAGE_L1, "Line 1"),
        HughesPowerWatchdogCurrentSensor(config_entry, SENSOR_CURRENT_L1, "Line 1"),
        HughesPowerWatchdogPowerSensor(config_entry, SENSOR_POWER_L1, "Line 1"),
        HughesPowerWatchdogVoltageSensor(config_entry, SENSOR_VOLTAGE_L2, "Line 2"),
        HughesPowerWatchdogCurrentSensor(config_entry, SENSOR_CURRENT_L2, "Line 2"),
        HughesPowerWatchdogPowerSensor(config_entry, SENSOR_POWER_L2, "Line 2"),
        HughesPowerWatchdogPowerSensor(
            config_entry, SENSOR_COMBINED_POWER, "Combined"
        ),
        HughesPowerWatchdogEnergySensor(config_entry),
        HughesPowerWatchdogErrorCodeSensor(config_entry),
        HughesPowerWatchdogErrorTextSensor(config_entry),
    ]

    async_add_entities(sensors)


class HughesPowerWatchdogSensor(SensorEntity):
    """Base class for Hughes Power Watchdog sensors."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: ConfigEntry, sensor_type: str) -> None:
        """Initialize the sensor."""
        self._config_entry = config_entry
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"


class HughesPowerWatchdogVoltageSensor(HughesPowerWatchdogSensor):
    """Voltage sensor for Hughes Power Watchdog."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, config_entry: ConfigEntry, sensor_type: str, line: str
    ) -> None:
        """Initialize voltage sensor."""
        super().__init__(config_entry, sensor_type)
        self._attr_name = f"Voltage {line}"


class HughesPowerWatchdogCurrentSensor(HughesPowerWatchdogSensor):
    """Current sensor for Hughes Power Watchdog."""

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self, config_entry: ConfigEntry, sensor_type: str, line: str
    ) -> None:
        """Initialize current sensor."""
        super().__init__(config_entry, sensor_type)
        self._attr_name = f"Current {line}"


class HughesPowerWatchdogPowerSensor(HughesPowerWatchdogSensor):
    """Power sensor for Hughes Power Watchdog."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, config_entry: ConfigEntry, sensor_type: str, line: str
    ) -> None:
        """Initialize power sensor."""
        super().__init__(config_entry, sensor_type)
        self._attr_name = f"Power {line}"


class HughesPowerWatchdogEnergySensor(HughesPowerWatchdogSensor):
    """Energy sensor for Hughes Power Watchdog."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize energy sensor."""
        super().__init__(config_entry, SENSOR_TOTAL_POWER)
        self._attr_name = "Cumulative Power Usage"


class HughesPowerWatchdogErrorCodeSensor(HughesPowerWatchdogSensor):
    """Error code sensor for Hughes Power Watchdog."""

    _attr_icon = "mdi:alert-circle"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize error code sensor."""
        super().__init__(config_entry, SENSOR_ERROR_CODE)
        self._attr_name = "Error Code"


class HughesPowerWatchdogErrorTextSensor(HughesPowerWatchdogSensor):
    """Error text sensor for Hughes Power Watchdog."""

    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize error text sensor."""
        super().__init__(config_entry, SENSOR_ERROR_TEXT)
        self._attr_name = "Error Description"
