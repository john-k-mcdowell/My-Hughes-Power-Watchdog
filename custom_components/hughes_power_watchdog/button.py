"""Button platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    BUTTON_ENERGY_RESET,
    BUTTON_ERROR_DELETE,
    BUTTON_TRIP_RESTART,
    DOMAIN,
)
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

    # Command entities are only exposed on V2 devices. V1 command support is
    # still being reverse-engineered — writes succeed but the device ignores them.
    # The one exception is the V1 restart after trip, whose wire format is known.
    if not coordinator.is_v2_protocol:
        async_add_entities([HughesPowerWatchdogTripRestartButton(coordinator)])
        return

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


def _timestamp_to_iso(timestamp: float | None) -> str | None:
    """Convert a Unix timestamp to an ISO 8601 UTC string, or None."""
    if timestamp is None:
        return None
    return dt_util.utc_from_timestamp(timestamp).isoformat()


class HughesPowerWatchdogTripRestartButton(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], ButtonEntity
):
    """Restart after trip button for V1 (Gen 1) Hughes Power Watchdogs.

    Sends the same "RELAY ON" command as the restart button in the official
    Gen 1 app, restoring power after an E3/E4 (over-current) or E8
    (neutral missing) trip. Pressing it while no such error is active
    is refused and nothing is sent.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart-alert"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the restart after trip button."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{BUTTON_TRIP_RESTART}"
        )
        self._attr_name = "Restart After Trip"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last command sent and the device's reply."""
        info = self.coordinator.trip_restart_info
        return {
            "last_sent": _timestamp_to_iso(info["last_sent"]),
            "last_reply": info["last_reply"],
            "last_reply_time": _timestamp_to_iso(info["last_reply_time"]),
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.coordinator.active_trip_code is None:
            raise HomeAssistantError(
                f"No trip to restart from (error code {self.coordinator.error_code}); restart "
                "is only sent for E3/E4 (over-current) or E8 (neutral missing)"
            )
        if not await self.coordinator.async_restart_after_trip():
            raise HomeAssistantError(
                "Failed to send restart after trip to the Power Watchdog"
            )
        self.async_write_ha_state()
