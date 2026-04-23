"""Switch platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONNECTION_CHECK_INTERVAL,
    DOMAIN,
    SENSOR_RELAY_STATUS,
    SWITCH_MONITORING,
    SWITCH_NEUTRAL_DETECTION_CONTROL,
    SWITCH_RELAY,
)
from .coordinator import HughesPowerWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog switches."""
    coordinator: HughesPowerWatchdogCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities = [
        HughesPowerWatchdogMonitoringSwitch(coordinator),
    ]

    # Command entities are only exposed on V2 devices. V1 command support is
    # still being reverse-engineered — writes succeed but the device ignores them.
    if coordinator.is_v2_protocol:
        entities.append(HughesPowerWatchdogRelaySwitch(coordinator))
        entities.append(HughesPowerWatchdogNeutralDetectionControlSwitch(coordinator))

    async_add_entities(entities)


class HughesPowerWatchdogMonitoringSwitch(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], SwitchEntity
):
    """Monitoring switch for Hughes Power Watchdog."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:connection"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the monitoring switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{SWITCH_MONITORING}"
        self._attr_name = "Monitoring"
        self._attr_device_info = coordinator.device_info
        self._attr_is_on = coordinator.monitoring_enabled

    @property
    def is_on(self) -> bool:
        """Return true if monitoring is enabled."""
        return self.coordinator.monitoring_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on - enable monitoring."""
        from datetime import timedelta

        # Resume connection watchdog
        self.coordinator.update_interval = timedelta(seconds=CONNECTION_CHECK_INTERVAL)

        # Restart background tasks and reconnect
        self.coordinator.start_monitoring()

        await self.coordinator.async_refresh()
        self.async_write_ha_state()
        _LOGGER.debug("Monitoring enabled for %s", self.coordinator.address)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off - disable monitoring."""
        # Stop connection watchdog
        self.coordinator.update_interval = None

        # Unsubscribe, disconnect, and cleanup
        await self.coordinator.async_disconnect()

        self.async_write_ha_state()
        _LOGGER.debug("Monitoring disabled for %s", self.coordinator.address)


class HughesPowerWatchdogRelaySwitch(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], SwitchEntity
):
    """Power relay switch for Hughes Power Watchdog.

    Controls the main power relay on the device.
    V2: SetOpen command with explicit ON/OFF.
    V1: "relayOn" toggle command.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:electric-switch"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the relay switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{SWITCH_RELAY}"
        self._attr_name = "Power Relay"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return True if relay is on (power flowing).

        V2: reads relay status from data (0x00 = ON).
        V1: no relay status reported, assume on unless error.
        """
        if self.coordinator.is_v2_protocol:
            val = self.coordinator.data.get(SENSOR_RELAY_STATUS)
            if val is None:
                return None
            return val == 0x00
        # V1 doesn't report relay status; assume on
        return True

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn relay on."""
        await self.coordinator.async_set_relay(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn relay off."""
        await self.coordinator.async_set_relay(False)
        self.async_write_ha_state()


class HughesPowerWatchdogNeutralDetectionControlSwitch(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], SwitchEntity
):
    """Neutral detection control switch for Hughes Power Watchdog (V2 only).

    Controls whether the device monitors for neutral wiring issues.
    Distinct from the NeutralDetection binary sensor which shows current status.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the neutral detection control switch."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{SWITCH_NEUTRAL_DETECTION_CONTROL}"
        )
        self._attr_name = "Neutral Detection Control"
        self._attr_device_info = coordinator.device_info
        # Assume enabled by default (device default state)
        self._assumed_on: bool = True

    @property
    def is_on(self) -> bool:
        """Return True if neutral detection monitoring is enabled."""
        return self._assumed_on

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable neutral detection monitoring."""
        success = await self.coordinator.async_set_neutral_detection(True)
        if success:
            self._assumed_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable neutral detection monitoring."""
        success = await self.coordinator.async_set_neutral_detection(False)
        if success:
            self._assumed_on = False
        self.async_write_ha_state()
