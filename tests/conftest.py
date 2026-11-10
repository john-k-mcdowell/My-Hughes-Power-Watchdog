"""Fixtures for Hughes Power Watchdog tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hughes_power_watchdog.const import DOMAIN

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


@pytest.fixture
def make_coordinator(
    hass: HomeAssistant,
    tracked_coordinators: list[HughesPowerWatchdogCoordinator],
):
    """Build a coordinator without background tasks; shut down after the test."""

    def factory(
        name: str = "PMS0000000000000000", **entry_data: object
    ) -> HughesPowerWatchdogCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=name,
            data={"address": "AA:BB:CC:DD:EE:FF", **entry_data},
        )
        entry.add_to_hass(hass)
        with patch.object(HughesPowerWatchdogCoordinator, "_start_background_tasks"):
            coordinator = HughesPowerWatchdogCoordinator(hass, entry)
        tracked_coordinators.append(coordinator)
        return coordinator

    return factory
