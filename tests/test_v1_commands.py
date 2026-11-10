"""Tests for the V1 (Gen 1) energy reset and backlight commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError

from custom_components.hughes_power_watchdog.button import (
    HughesPowerWatchdogEnergyResetButton,
    HughesPowerWatchdogErrorDeleteButton,
    HughesPowerWatchdogTripRestartButton,
    async_setup_entry as button_setup_entry,
)
from custom_components.hughes_power_watchdog.const import DOMAIN, SENSOR_TOTAL_POWER
from custom_components.hughes_power_watchdog.light import (
    HughesPowerWatchdogBacklightLight,
    async_setup_entry as light_setup_entry,
)

from .fakes import fake_v1_client
from .packets import v1_packet


@pytest.fixture
def v1(make_coordinator):
    """Return a V1 coordinator wired to a fake BLE client, and that client."""
    coordinator = make_coordinator("PMS0000000000000000")
    client = fake_v1_client(["write", "write-without-response"])
    coordinator._ensure_connected = AsyncMock(return_value=client)
    return coordinator, client


# --- energy reset ------------------------------------------------------------


async def test_v1_energy_reset_writes_resets_string(v1) -> None:
    """V1 energy reset writes the app's 'RESEt' string to 0xFFF5."""
    coordinator, client = v1
    assert await coordinator.async_reset_energy() is True
    client.write_gatt_char.assert_awaited_once_with(
        client.write_char, b"RESEt", response=False
    )
    assert coordinator.v1_command_info["last_command"] == "energy reset"


async def test_v1_energy_reset_withholds_total(v1) -> None:
    """After a reset the total waits for Line 2 to report its own counter."""
    coordinator, _ = v1
    coordinator._line_2_energy = 50.0
    assert await coordinator.async_reset_energy() is True
    assert coordinator._line_2_energy is None


async def test_v1_energy_reset_failure_keeps_total(v1) -> None:
    """A failed write must not discard the known Line 2 energy."""
    coordinator, client = v1
    coordinator._line_2_energy = 50.0
    client.write_gatt_char.side_effect = BleakError("write failed")
    assert await coordinator.async_reset_energy() is False
    assert coordinator._line_2_energy == 50.0
    assert coordinator.v1_command_info["last_command"] is None


async def test_v1_energy_reset_refused_when_monitoring_off(v1) -> None:
    """Nothing is written while monitoring is off."""
    coordinator, client = v1
    coordinator._monitoring_enabled = False
    assert await coordinator.async_reset_energy() is False
    client.write_gatt_char.assert_not_awaited()


async def test_v2_energy_reset_does_not_use_v1_path(make_coordinator) -> None:
    """V2 devices keep using the V2 command."""
    coordinator = make_coordinator("WD_V5_000000000000")
    coordinator._send_v2_command = AsyncMock(return_value=True)
    coordinator._send_v1_wire_command = AsyncMock()
    assert await coordinator.async_reset_energy() is True
    coordinator._send_v2_command.assert_awaited_once()
    coordinator._send_v1_wire_command.assert_not_awaited()


# --- backlight ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "payload"),
    [(0, b"SET:BL\x00"), (1, b"SET:BL\x01"), (4, b"SET:BL\x04"), (-3, b"SET:BL\x00"), (9, b"SET:BL\x04")],
)
async def test_v1_backlight_payload_and_clamping(v1, level: int, payload: bytes) -> None:
    """The level is clamped to 0-4 and sent as 'SET:BL' + one raw byte."""
    coordinator, client = v1
    assert await coordinator.async_set_backlight(level) is True
    client.write_gatt_char.assert_awaited_once_with(
        client.write_char, payload, response=False
    )


async def test_v2_backlight_does_not_use_v1_path(make_coordinator) -> None:
    """V2 devices keep using the V2 command with their 0-5 range."""
    coordinator = make_coordinator("WD_V5_000000000000")
    coordinator._send_v2_command = AsyncMock(return_value=True)
    coordinator._send_v1_wire_command = AsyncMock()
    assert await coordinator.async_set_backlight(5) is True
    coordinator._send_v1_wire_command.assert_not_awaited()


# --- acknowledgments ----------------------------------------------------------


async def test_v1_command_info_records_reply(v1) -> None:
    """The command and the device's ack are both visible afterwards."""
    coordinator, _ = v1
    assert coordinator.v1_command_info["last_command"] is None

    await coordinator.async_set_backlight(3)
    coordinator._notification_handler_v1(0, bytearray(b"set:bl3"))

    info = coordinator.v1_command_info
    assert info["last_command"] == "backlight level 3"
    assert info["last_command_sent"] is not None
    assert info["last_reply"] == "set:bl3"
    assert info["last_reply_time"] is not None


async def test_undecoded_v1_bytes_do_not_break_parsing(v1) -> None:
    """The diagnostic logging of bytes 20-30 / 35-36 must not affect parsing."""
    coordinator, _ = v1
    packet = bytearray(v1_packet(1, energy=7.0))
    packet[20:31] = bytes(range(11))
    packet[35:37] = b"\xaa\xbb"
    coordinator._notification_handler_v1(0, bytearray(packet[:20]))
    coordinator._notification_handler_v1(0, bytearray(packet[20:]))
    assert coordinator.data[SENSOR_TOTAL_POWER] == 7.0


# --- entities ----------------------------------------------------------------


async def test_button_platform_v1_and_v2(hass: HomeAssistant, make_coordinator) -> None:
    """V1 gets restart + reset buttons, never error delete; V2 never gets restart."""
    v1 = make_coordinator("PMS0000000000000000")
    v2 = make_coordinator("WD_V5_000000000000")
    for coordinator in (v1, v2):
        hass.data.setdefault(DOMAIN, {})[coordinator.config_entry.entry_id] = coordinator

    added_v1: list = []
    await button_setup_entry(hass, v1.config_entry, lambda e: added_v1.extend(e))
    assert {type(e) for e in added_v1} == {
        HughesPowerWatchdogTripRestartButton,
        HughesPowerWatchdogEnergyResetButton,
    }

    added_v2: list = []
    await button_setup_entry(hass, v2.config_entry, lambda e: added_v2.extend(e))
    assert {type(e) for e in added_v2} == {
        HughesPowerWatchdogEnergyResetButton,
        HughesPowerWatchdogErrorDeleteButton,
    }


async def test_reset_button_attributes_v1_only(v1, make_coordinator) -> None:
    """The reset button shows the V1 command/reply attributes, none on V2."""
    coordinator, _ = v1
    attrs = HughesPowerWatchdogEnergyResetButton(coordinator).extra_state_attributes
    assert attrs == {
        "last_command": None,
        "last_command_sent": None,
        "last_reply": None,
        "last_reply_time": None,
    }

    v2 = make_coordinator("WD_V5_000000000000")
    assert HughesPowerWatchdogEnergyResetButton(v2).extra_state_attributes is None


async def test_reset_button_press_sends_command(v1) -> None:
    """Pressing the V1 reset button writes the command."""
    coordinator, client = v1
    await HughesPowerWatchdogEnergyResetButton(coordinator).async_press()
    client.write_gatt_char.assert_awaited_once()


async def test_light_platform_adds_light_on_v1_and_v2(
    hass: HomeAssistant, make_coordinator
) -> None:
    """Both generations get the backlight light."""
    for name in ("PMS0000000000000000", "WD_V5_000000000000"):
        coordinator = make_coordinator(name)
        hass.data.setdefault(DOMAIN, {})[coordinator.config_entry.entry_id] = coordinator
        added: list = []
        await light_setup_entry(hass, coordinator.config_entry, lambda e: added.extend(e))
        assert [type(e) for e in added] == [HughesPowerWatchdogBacklightLight]


def _light(hass: HomeAssistant, coordinator) -> HughesPowerWatchdogBacklightLight:
    light = HughesPowerWatchdogBacklightLight(coordinator)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    return light


async def test_v1_light_is_assumed_state_with_max_four(hass, v1) -> None:
    """V1 has no readback, so the state is assumed and levels run 0-4."""
    coordinator, _ = v1
    light = _light(hass, coordinator)
    assert light.assumed_state is True
    assert light.is_on is None  # unknown until set or restored
    assert light._max_level == 4


async def test_v2_light_is_not_assumed(hass, make_coordinator) -> None:
    """V2 reads the level from the data stream."""
    light = _light(hass, make_coordinator("WD_V5_000000000000"))
    assert light.assumed_state is False
    assert light.extra_state_attributes is None


async def test_v1_light_turn_on_maps_brightness_to_levels(hass, v1) -> None:
    """HA brightness maps to levels 1-4 and 'on' without brightness is full."""
    coordinator, client = v1
    light = _light(hass, coordinator)

    await light.async_turn_on(**{ATTR_BRIGHTNESS: 255})
    assert client.write_gatt_char.await_args.args[1] == b"SET:BL\x04"
    await light.async_turn_on(**{ATTR_BRIGHTNESS: 64})
    assert client.write_gatt_char.await_args.args[1] == b"SET:BL\x01"
    await light.async_turn_on(**{ATTR_BRIGHTNESS: 1})  # never turns on at level 0
    assert client.write_gatt_char.await_args.args[1] == b"SET:BL\x01"
    await light.async_turn_on()
    assert client.write_gatt_char.await_args.args[1] == b"SET:BL\x04"
    assert light.is_on is True


async def test_v1_light_turn_off_sends_level_zero(hass, v1) -> None:
    """Turning off sends level 0 and updates the assumed state."""
    coordinator, client = v1
    light = _light(hass, coordinator)
    await light.async_turn_on()
    await light.async_turn_off()

    assert client.write_gatt_char.await_args.args[1] == b"SET:BL\x00"
    assert light.is_on is False
    assert light.brightness == 0
    assert light.async_write_ha_state.call_count == 2


async def test_v1_light_failure_raises_and_keeps_state(hass, v1) -> None:
    """A failed write raises and leaves the assumed level unchanged."""
    coordinator, client = v1
    light = _light(hass, coordinator)
    await light.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    level = light._last_set_level

    client.write_gatt_char.side_effect = BleakError("write failed")
    with pytest.raises(HomeAssistantError):
        await light.async_turn_off()
    assert light._last_set_level == level


@pytest.mark.parametrize(
    ("state", "attrs", "expected"),
    [
        ("off", {}, 0),
        ("on", {ATTR_BRIGHTNESS: 255}, 4),
        ("on", {ATTR_BRIGHTNESS: 128}, 2),
        ("on", {}, None),
        ("unavailable", {}, None),
    ],
)
async def test_v1_light_restores_level(hass, v1, state, attrs, expected) -> None:
    """The last-set level survives a restart."""
    coordinator, _ = v1
    light = _light(hass, coordinator)
    light._restore_level(State("light.test", state, attrs))
    assert light._last_set_level == expected


async def test_v1_light_restore_with_no_history(hass, v1) -> None:
    """No previous state leaves the level unknown."""
    coordinator, _ = v1
    light = _light(hass, coordinator)
    light._restore_level(None)
    assert light._last_set_level is None
