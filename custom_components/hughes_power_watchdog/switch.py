"""Switch platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SWITCH_MONITORING

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog switches."""
    async_add_entities([HughesPowerWatchdogMonitoringSwitch(config_entry)])


class HughesPowerWatchdogMonitoringSwitch(SwitchEntity):
    """Monitoring switch for Hughes Power Watchdog."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:connection"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the monitoring switch."""
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{SWITCH_MONITORING}"
        self._attr_name = "Monitoring"
        self._attr_is_on = True

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._attr_is_on = True
        self.async_write_ha_state()
        # TODO: Implement BLE connection logic

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._attr_is_on = False
        self.async_write_ha_state()
        # TODO: Implement BLE disconnection logic
