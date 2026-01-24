"""Switch platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SWITCH_MONITORING
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

    async_add_entities([HughesPowerWatchdogMonitoringSwitch(coordinator)])


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
        self._attr_is_on = coordinator.update_interval is not None

    @property
    def is_on(self) -> bool:
        """Return true if monitoring is enabled."""
        return self.coordinator.update_interval is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on - enable monitoring."""
        from datetime import timedelta
        from .const import DEFAULT_SCAN_INTERVAL

        # Resume coordinator updates
        self.coordinator.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

        # Restart background tasks (command worker, health monitor)
        self.coordinator.start_monitoring()

        await self.coordinator.async_refresh()
        self.async_write_ha_state()
        _LOGGER.debug("Monitoring enabled for %s", self.coordinator.address)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off - disable monitoring."""
        # Pause coordinator updates by setting interval to None
        self.coordinator.update_interval = None

        # Disconnect from device
        await self.coordinator.async_disconnect()

        self.async_write_ha_state()
        _LOGGER.debug("Monitoring disabled for %s", self.coordinator.address)
