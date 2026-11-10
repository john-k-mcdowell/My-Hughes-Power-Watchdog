"""Tests for the V1 (Gen 1) restart after trip command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from bleak.exc import BleakError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.hughes_power_watchdog.button import (
    HughesPowerWatchdogEnergyResetButton,
    HughesPowerWatchdogErrorDeleteButton,
    HughesPowerWatchdogTripRestartButton,
    async_setup_entry as button_setup_entry,
)
from custom_components.hughes_power_watchdog.const import DOMAIN, V1_TRIP_LATCH_SECONDS

from .fakes import FFE0, FFE2, FFF5, fake_v1_client as _client
from .packets import v1_packet
from custom_components.hughes_power_watchdog.coordinator import (
    HughesPowerWatchdogCoordinator,
)



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


# --- characteristic lookup and failure paths --------------------------------


async def test_refused_when_characteristic_missing(coordinator_factory) -> None:
    """Nothing is sent if the device has no 0xFFF5 characteristic at all."""
    coordinator, client = coordinator_factory()
    client.services[1].characteristics = [
        c for c in client.services[1].characteristics if c.uuid != FFF5
    ]
    assert await coordinator.async_restart_after_trip() is False
    client.write_gatt_char.assert_not_awaited()


async def test_ignores_characteristic_in_non_vendor_service(
    coordinator_factory,
) -> None:
    """0xFFF5 under a standard (non-0000Fxxx) service is not the command channel."""
    coordinator, _ = coordinator_factory()
    other = _client(["write", "write-without-response"], service_uuid=FFE0[:4] + "1800" + FFE0[8:])
    coordinator._ensure_connected = AsyncMock(return_value=other)

    assert await coordinator.async_restart_after_trip() is False
    other.write_gatt_char.assert_not_awaited()


async def test_ble_write_error_returns_false(coordinator_factory) -> None:
    """A BLE write failure is reported as a failed command, not raised."""
    coordinator, client = coordinator_factory()
    client.write_gatt_char.side_effect = BleakError("write failed")
    assert await coordinator.async_restart_after_trip() is False
    assert coordinator.trip_restart_info["last_sent"] is None


async def test_connection_failure_returns_false(coordinator_factory) -> None:
    """Failing to connect is reported as a failed command."""
    coordinator, _ = coordinator_factory()
    coordinator._ensure_connected = AsyncMock(side_effect=UpdateFailed("no device"))
    assert await coordinator.async_restart_after_trip() is False


# --- command acknowledgments on 0xFFE2 --------------------------------------


@pytest.mark.parametrize(
    "reply", [b"relay on", b"RESET", b"del:recA", b"set:t", b"set:bl3"]
)
async def test_known_replies_are_not_buffered(
    coordinator_factory, reply: bytes
) -> None:
    """Every known ASCII ack is recorded and kept out of the data buffer."""
    coordinator, _ = coordinator_factory()
    coordinator._notification_handler_v1(0, bytearray(reply))

    assert coordinator.trip_restart_info["last_reply"] == reply.decode()
    assert len(coordinator._data_buffer) == 0


async def test_reply_between_chunks_does_not_corrupt_packet(
    coordinator_factory,
) -> None:
    """An ack arriving mid-packet leaves the half-filled buffer intact."""
    coordinator, _ = coordinator_factory(error_code=0)
    packet = v1_packet(1, voltage=121.5, energy=42.0)

    coordinator._notification_handler_v1(0, bytearray(packet[:20]))
    coordinator._notification_handler_v1(0, bytearray(b"relay on"))
    assert len(coordinator._data_buffer) == 20
    coordinator._notification_handler_v1(0, bytearray(packet[20:]))

    assert coordinator.data["voltage_line_1"] == pytest.approx(121.5)
    assert coordinator.data["total_power"] == pytest.approx(42.0)
    assert coordinator.trip_restart_info["last_reply"] == "relay on"


# --- button entity and platform setup ---------------------------------------


async def test_button_press_writes_state(hass: HomeAssistant, coordinator_factory) -> None:
    """A successful press refreshes the entity state."""
    coordinator, _ = coordinator_factory()
    button = HughesPowerWatchdogTripRestartButton(coordinator)
    button.hass = hass
    button.async_write_ha_state = MagicMock()

    await button.async_press()
    button.async_write_ha_state.assert_called_once()


async def test_button_press_failure_raises(coordinator_factory) -> None:
    """A failed write surfaces as a HomeAssistantError."""
    coordinator, client = coordinator_factory()
    client.write_gatt_char.side_effect = BleakError("write failed")
    button = HughesPowerWatchdogTripRestartButton(coordinator)
    with pytest.raises(HomeAssistantError):
        await button.async_press()


async def test_button_identity_and_availability(coordinator_factory) -> None:
    """Stable unique ID, device info, and availability follow monitoring."""
    coordinator, _ = coordinator_factory()
    button = HughesPowerWatchdogTripRestartButton(coordinator)

    assert button.unique_id == f"{coordinator.config_entry.entry_id}_trip_restart"
    assert button.has_entity_name is True
    assert button.device_info == coordinator.device_info

    coordinator.last_update_success = True
    coordinator._monitoring_enabled = True
    assert button.available is True
    coordinator._monitoring_enabled = False
    assert button.available is False


async def test_button_attributes_before_any_command(coordinator_factory) -> None:
    """Attributes are None until a command is sent and answered."""
    coordinator, _ = coordinator_factory()
    attrs = HughesPowerWatchdogTripRestartButton(coordinator).extra_state_attributes
    assert attrs == {"last_sent": None, "last_reply": None, "last_reply_time": None}


async def test_platform_adds_trip_button_only_on_v1(
    hass: HomeAssistant, coordinator_factory
) -> None:
    """V1 gets the restart and energy reset buttons; V2 never gets the restart one."""
    v1, _ = coordinator_factory(name="PMS0000000000000000")
    hass.data.setdefault(DOMAIN, {})[v1.config_entry.entry_id] = v1
    added: list = []
    await button_setup_entry(hass, v1.config_entry, lambda ents: added.extend(ents))
    assert {type(e) for e in added} == {
        HughesPowerWatchdogTripRestartButton,
        HughesPowerWatchdogEnergyResetButton,
    }

    v2, _ = coordinator_factory(name="WD_V5_000000000000")
    hass.data[DOMAIN][v2.config_entry.entry_id] = v2
    added_v2: list = []
    await button_setup_entry(hass, v2.config_entry, lambda ents: added_v2.extend(ents))
    assert added_v2
    assert not any(isinstance(e, HughesPowerWatchdogTripRestartButton) for e in added_v2)


async def test_other_buttons_raise_on_failure(coordinator_factory) -> None:
    """Energy reset and error delete report a failed command to the user."""
    coordinator, _ = coordinator_factory(name="WD_V5_000000000000")
    coordinator.async_reset_energy = AsyncMock(return_value=False)
    coordinator.async_delete_errors = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError):
        await HughesPowerWatchdogEnergyResetButton(coordinator).async_press()
    with pytest.raises(HomeAssistantError):
        await HughesPowerWatchdogErrorDeleteButton(coordinator).async_press()

    coordinator.async_reset_energy.return_value = True
    coordinator.async_delete_errors.return_value = True
    await HughesPowerWatchdogEnergyResetButton(coordinator).async_press()
    await HughesPowerWatchdogErrorDeleteButton(coordinator).async_press()
