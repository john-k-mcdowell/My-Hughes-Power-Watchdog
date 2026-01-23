"""The Hughes Power Watchdog integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import HughesPowerWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hughes Power Watchdog from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create coordinator
    coordinator = HughesPowerWatchdogCoordinator(hass, entry)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator in hass.data
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Disconnect from device
    coordinator: HughesPowerWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_disconnect()

    # Unload platforms
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
