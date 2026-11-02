"""Tests for the V1 (Gen 1) restart after trip command."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hughes_power_watchdog.button import (
    HughesPowerWatchdogTripRestartButton,
)
from custom_components.hughes_power_watchdog.const import DOMAIN, V1_TRIP_LATCH_SECONDS
from custom_components.hughes_power_watchdog.coordinator import (
    HughesPowerWatchdogCoordinator,
)

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE2 = "0000ffe2-0000-1000-8000-00805f9b34fb"
FFF5 = "0000fff5-0000-1000-8000-00805f9b34fb"


def _client(properties: list[str], service_uuid: str = FFE0) -> MagicMock:
    """Return a fake BleakClient with a V1-style GATT table."""
    write_char = SimpleNamespace(uuid=FFF5, properties=properties)
    services = [
        SimpleNamespace(
            uuid="00001800-0000-1000-8000-00805f9b34fb", characteristics=[]
        ),
        SimpleNamespace(
            uuid=service_uuid,
            characteristics=[
                SimpleNamespace(uuid=FFE2, properties=["notify"]),
                write_char,
            ],
        ),
    ]
    client = MagicMock()
    client.services = services
    client.write_gatt_char = AsyncMock()
    client.write_char = write_char
    return client


def _coordinator(
    hass: HomeAssistant,
    tracked: list[HughesPowerWatchdogCoordinator],
    name: str = "PMS0000000000000000",
    error_code: int = 3,
    properties: list[str] | None = None,
) -> tuple[HughesPowerWatchdogCoordinator, MagicMock]:
    """Return a coordinator wired to a fake BLE client.

    The real command worker and health monitor are not started. Restart after
    trip writes the characteristic directly, so those loops are unused here.
    Left running they outlive the test and ``_process_commands`` then logs
    "Queue is bound to a different event loop" without waiting.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, title=name, data={"address": "AA:BB:CC:DD:EE:FF"}
    )
    entry.add_to_hass(hass)
    with patch.object(HughesPowerWatchdogCoordinator, "_start_background_tasks"):
        coordinator = HughesPowerWatchdogCoordinator(hass, entry)
    # Outside of entry setup DataUpdateCoordinator resets config_entry to None
    coordinator.config_entry = entry
    coordinator._record_v1_error_code(error_code)
    client = _client(
        ["write", "write-without-response"] if properties is None else properties
    )
    coordinator._ensure_connected = AsyncMock(return_value=client)
    tracked.append(coordinator)
    return coordinator, client


@pytest.fixture
def coordinator_factory(
    hass: HomeAssistant,
    tracked_coordinators: list[HughesPowerWatchdogCoordinator],
):
    """Build coordinators that the shutdown fixture will stop."""

    def factory(
        *,
        name: str = "PMS0000000000000000",
        error_code: int = 3,
        properties: list[str] | None = None,
    ) -> tuple[HughesPowerWatchdogCoordinator, MagicMock]:
        return _coordinator(
            hass,
            tracked_coordinators,
            name=name,
            error_code=error_code,
            properties=properties,
        )

    return factory


@pytest.mark.parametrize("error_code", [3, 4, 8])
async def test_sends_relay_on_for_trip_errors(
    coordinator_factory, error_code: int
) -> None:
    """RELAY ON is written to 0xFFF5 for E3/E4/E8."""
    coordinator, client = coordinator_factory(error_code=error_code)
    assert not coordinator.is_v2_protocol

    assert await coordinator.async_restart_after_trip() is True
    client.write_gatt_char.assert_awaited_once_with(
        client.write_char, b"RELAY ON", response=False
    )
    assert coordinator.trip_restart_info["last_sent"] is not None


async def test_uses_write_with_response_when_only_option(
    coordinator_factory,
) -> None:
    """Falls back to write-with-response like Android's default write type."""
    coordinator, client = coordinator_factory(properties=["write"])
    assert await coordinator.async_restart_after_trip() is True
    client.write_gatt_char.assert_awaited_once_with(
        client.write_char, b"RELAY ON", response=True
    )


@pytest.mark.parametrize("error_code", [0, 1, 2, 5, 6, 7, 9])
async def test_refused_without_trip(coordinator_factory, error_code: int) -> None:
    """Nothing is sent unless the device reports E3/E4/E8."""
    coordinator, client = coordinator_factory(error_code=error_code)
    assert await coordinator.async_restart_after_trip() is False
    client.write_gatt_char.assert_not_awaited()


async def test_refused_when_monitoring_off(coordinator_factory) -> None:
    """Nothing is sent while monitoring is disabled."""
    coordinator, client = coordinator_factory()
    coordinator._monitoring_enabled = False
    assert await coordinator.async_restart_after_trip() is False
    client.write_gatt_char.assert_not_awaited()


async def test_refused_on_v2(coordinator_factory) -> None:
    """V2 (Gen 2) devices never get the V1 command."""
    coordinator, client = coordinator_factory(name="WD_V5_000000000000")
    assert coordinator.is_v2_protocol
    assert await coordinator.async_restart_after_trip() is False
    client.write_gatt_char.assert_not_awaited()


async def test_refused_without_writable_characteristic(coordinator_factory) -> None:
    """Nothing is sent if 0xFFF5 is missing or not writable."""
    coordinator, client = coordinator_factory(properties=["read"])
    assert await coordinator.async_restart_after_trip() is False
    client.write_gatt_char.assert_not_awaited()


async def test_trip_latched_across_line_packets(coordinator_factory) -> None:
    """A trip seen on one line's packet survives a clean packet from the other."""
    coordinator, client = coordinator_factory(error_code=3)
    coordinator._record_v1_error_code(0)  # other line's packet reports no error
    assert coordinator.error_code == 0
    assert coordinator.active_trip_code == 3

    assert await coordinator.async_restart_after_trip() is True
    client.write_gatt_char.assert_awaited_once()


async def test_trip_latch_expires(coordinator_factory) -> None:
    """The latch only holds for V1_TRIP_LATCH_SECONDS."""
    coordinator, client = coordinator_factory(error_code=4)
    latched_at = coordinator._trip_latch[1]
    with patch(
        "custom_components.hughes_power_watchdog.coordinator.time.time",
        return_value=latched_at + V1_TRIP_LATCH_SECONDS + 1,
    ):
        assert coordinator.active_trip_code is None
        assert await coordinator.async_restart_after_trip() is False
    client.write_gatt_char.assert_not_awaited()


async def test_reply_is_recorded_and_not_buffered(coordinator_factory) -> None:
    """The 'relay on' ack is recorded and kept out of the data buffer."""
    coordinator, _ = coordinator_factory()
    coordinator._notification_handler_v1(0, bytearray(b"relay on"))

    info = coordinator.trip_restart_info
    assert info["last_reply"] == "relay on"
    assert info["last_reply_time"] is not None
    assert len(coordinator._data_buffer) == 0

    # Regular 20-byte data chunks are still buffered as before
    coordinator._notification_handler_v1(0, bytearray(20))
    assert len(coordinator._data_buffer) == 20


async def test_button_press(hass: HomeAssistant, coordinator_factory) -> None:
    """The button sends the command and exposes the reply attributes."""
    coordinator, client = coordinator_factory()
    button = HughesPowerWatchdogTripRestartButton(coordinator)
    button.hass = hass
    button.async_write_ha_state = MagicMock()

    await button.async_press()
    client.write_gatt_char.assert_awaited_once()
    coordinator._notification_handler_v1(0, bytearray(b"relay on"))
    attrs = button.extra_state_attributes
    assert attrs["last_reply"] == "relay on"
    assert attrs["last_sent"] is not None
    assert attrs["last_reply_time"] is not None


async def test_button_press_without_trip_raises(coordinator_factory) -> None:
    """Pressing with no E3/E4/E8 active raises a user-visible error."""
    coordinator, client = coordinator_factory(error_code=0)
    button = HughesPowerWatchdogTripRestartButton(coordinator)
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    client.write_gatt_char.assert_not_awaited()
