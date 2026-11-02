"""Fixtures for Hughes Power Watchdog tests."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.hughes_power_watchdog.coordinator import (
    HughesPowerWatchdogCoordinator,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield


@pytest.fixture
def tracked_coordinators() -> list[HughesPowerWatchdogCoordinator]:
    """Coordinators a test constructed and must shut down."""
    return []


@pytest.fixture(autouse=True)
async def shutdown_tracked_coordinators(
    auto_enable_custom_integrations: object,
    hass: HomeAssistant,
    tracked_coordinators: list[HughesPowerWatchdogCoordinator],
):
    """Cancel coordinator work before Home Assistant closes its loop.

    Unit tests do not start the command worker or health monitor. Anything
    that still got started is cancelled here, and coordinator timers are
    dropped, while ``hass`` is still running. Doing this after the loop is
    replaced makes ``_process_commands`` raise "Queue is bound to a different
    event loop" and log that error forever.
    """
    # Fixture dependencies only: custom integrations load first, and this
    # teardown runs while the hass loop is still open.
    del auto_enable_custom_integrations, hass
    yield
    for coordinator in tracked_coordinators:
        await coordinator.async_disconnect()
        await coordinator.async_shutdown()
