"""Light platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    LIGHT_BACKLIGHT,
    SENSOR_BACKLIGHT,
    V1_BACKLIGHT_MAX,
    V2_BACKLIGHT_MAX,
)
from .coordinator import HughesPowerWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog light entities."""
    coordinator: HughesPowerWatchdogCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    async_add_entities([HughesPowerWatchdogBacklightLight(coordinator)])


def _timestamp_to_iso(timestamp: float | None) -> str | None:
    """Convert a Unix timestamp to an ISO 8601 UTC string, or None."""
    if timestamp is None:
        return None
    return dt_util.utc_from_timestamp(timestamp).isoformat()


class HughesPowerWatchdogBacklightLight(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], LightEntity, RestoreEntity
):
    """Backlight brightness control for Hughes Power Watchdog.

    Maps HA brightness (0-255) to discrete device levels:
    - V1: 0-4 (5 levels)
    - V2: 0-5 (6 levels)

    For V2 devices, current level is read from the data stream (byte 33).
    For V1 devices (experimental, untested on hardware) there is no known
    readback, so the last-set level is tracked locally, restored after a
    restart, and the state is marked as assumed. Whether level 0 turns the
    V1 LED off is not yet confirmed.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:brightness-6"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the backlight light entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{LIGHT_BACKLIGHT}"
        )
        self._attr_name = "Backlight"
        self._attr_device_info = coordinator.device_info
        self._max_level = (
            V2_BACKLIGHT_MAX
            if coordinator.is_v2_protocol
            else V1_BACKLIGHT_MAX
        )
        # Track last-set level for V1 (no feedback from device)
        self._last_set_level: int | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last-set V1 level, since the device cannot report it."""
        await super().async_added_to_hass()
        if not self.coordinator.is_v2_protocol:
            self._restore_level(await self.async_get_last_state())

    def _restore_level(self, last_state: State | None) -> None:
        """Set the V1 level from the last known Home Assistant state."""
        if last_state is None:
            return
        if last_state.state == "off":
            self._last_set_level = 0
        elif last_state.state == "on":
            brightness = last_state.attributes.get(ATTR_BRIGHTNESS)
            if brightness is not None:
                self._last_set_level = round(brightness / 255 * self._max_level)

    @property
    def assumed_state(self) -> bool:
        """Return True for V1, whose backlight level cannot be read back."""
        return not self.coordinator.is_v2_protocol

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the last V1 command sent and the device's reply (V1 only)."""
        if self.coordinator.is_v2_protocol:
            return None
        info = self.coordinator.v1_command_info
        return {
            "last_command": info["last_command"],
            "last_command_sent": _timestamp_to_iso(info["last_command_sent"]),
            "last_reply": info["last_reply"],
            "last_reply_time": _timestamp_to_iso(info["last_reply_time"]),
        }

    @property
    def _device_level(self) -> int | None:
        """Get current device backlight level (0 to max_level)."""
        if self.coordinator.is_v2_protocol:
            return self.coordinator.data.get(SENSOR_BACKLIGHT)
        return self._last_set_level

    @property
    def brightness(self) -> int | None:
        """Return HA brightness (0-255) from device level."""
        level = self._device_level
        if level is None:
            return None
        if level == 0:
            return 0
        return round(level / self._max_level * 255)

    @property
    def is_on(self) -> bool | None:
        """Return True if backlight is on (level > 0)."""
        level = self._device_level
        if level is None:
            return None
        return level > 0

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the backlight.

        If brightness is provided, map to nearest device level.
        Otherwise, set to max brightness.
        """
        if ATTR_BRIGHTNESS in kwargs:
            ha_brightness = kwargs[ATTR_BRIGHTNESS]
            level = round(ha_brightness / 255 * self._max_level)
            # Ensure at least level 1 when turning on
            level = max(1, level)
        else:
            level = self._max_level

        await self._set_level(level)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the backlight (set to level 0)."""
        await self._set_level(0)

    async def _set_level(self, level: int) -> None:
        """Send a backlight level to the device and update the entity state."""
        if not await self.coordinator.async_set_backlight(level):
            raise HomeAssistantError(
                "Failed to set the backlight level on the Power Watchdog"
            )
        self._last_set_level = level
        self.async_write_ha_state()
