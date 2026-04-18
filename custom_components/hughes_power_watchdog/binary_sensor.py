"""Binary sensor platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_BOOST_MODE,
    SENSOR_NEUTRAL_DETECTION,
    SENSOR_RELAY_STATUS,
)
from .coordinator import HughesPowerWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog binary sensors."""
    coordinator: HughesPowerWatchdogCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([
        HughesPowerWatchdogRelayStatusSensor(coordinator),
        HughesPowerWatchdogBoostModeSensor(coordinator),
        HughesPowerWatchdogNeutralDetectionSensor(coordinator),
    ])


class HughesPowerWatchdogBinarySensor(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], BinarySensorEntity
):
    """Base class for Hughes Power Watchdog binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: HughesPowerWatchdogCoordinator, sensor_type: str
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{sensor_type}"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
            and self.coordinator.data.get(self._sensor_type) is not None
        )


class HughesPowerWatchdogRelayStatusSensor(HughesPowerWatchdogBinarySensor):
    """Relay status binary sensor (V2 only).

    Relay status byte: 0x00 = ON (power flowing), 0x01 or 0x02 = OFF/Error (tripped).
    is_on = True means relay is ON (power flowing, normal operation).
    """

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_icon = "mdi:electric-switch"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize relay status sensor."""
        super().__init__(coordinator, SENSOR_RELAY_STATUS)
        self._attr_name = "Relay Status"

    @property
    def is_on(self) -> bool | None:
        """Return True if relay is ON (power flowing)."""
        val = self.coordinator.data.get(self._sensor_type)
        if val is None:
            return None
        return val == 0x00


class HughesPowerWatchdogBoostModeSensor(HughesPowerWatchdogBinarySensor):
    """Boost mode binary sensor (V2 only).

    Boost mode byte: 0 = off, 1 = active.
    """

    _attr_icon = "mdi:flash-alert"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize boost mode sensor."""
        super().__init__(coordinator, SENSOR_BOOST_MODE)
        self._attr_name = "Boost Mode"

    @property
    def is_on(self) -> bool | None:
        """Return True if boost mode is active."""
        val = self.coordinator.data.get(self._sensor_type)
        if val is None:
            return None
        return val == 1


class HughesPowerWatchdogNeutralDetectionSensor(HughesPowerWatchdogBinarySensor):
    """Neutral detection binary sensor (V2 only).

    Neutral detection byte: 0x00 = OK, non-zero = problem detected.
    is_on = True means a problem is detected (for BinarySensorDeviceClass.PROBLEM).
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize neutral detection sensor."""
        super().__init__(coordinator, SENSOR_NEUTRAL_DETECTION)
        self._attr_name = "Neutral Detection"

    @property
    def is_on(self) -> bool | None:
        """Return True if a neutral problem is detected."""
        val = self.coordinator.data.get(self._sensor_type)
        if val is None:
            return None
        return val != 0x00
