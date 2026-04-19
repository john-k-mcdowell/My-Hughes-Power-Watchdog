"""Button platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BUTTON_ENERGY_RESET, BUTTON_ERROR_DELETE, DOMAIN
from .coordinator import HughesPowerWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog buttons."""
    coordinator: HughesPowerWatchdogCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([
        HughesPowerWatchdogEnergyResetButton(coordinator),
        HughesPowerWatchdogErrorDeleteButton(coordinator),
    ])


class HughesPowerWatchdogEnergyResetButton(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], ButtonEntity
):
    """Energy reset button for Hughes Power Watchdog.

    Resets the cumulative kWh counter to zero.
    Works on both V1 and V2 devices.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the energy reset button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{BUTTON_ENERGY_RESET}"
        )
        self._attr_name = "Reset Energy Counter"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_reset_energy()


class HughesPowerWatchdogErrorDeleteButton(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], ButtonEntity
):
    """Error history delete button for Hughes Power Watchdog.

    Deletes all stored error records from the device.
    V2: ErrorDel with 0xFF payload. V1: "deleteAllRecord" command.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:delete-alert"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the error delete button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{BUTTON_ERROR_DELETE}"
        )
        self._attr_name = "Clear Error History"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_delete_errors()
