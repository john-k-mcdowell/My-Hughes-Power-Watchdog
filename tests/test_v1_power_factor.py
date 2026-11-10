"""Tests for the V1 power factor field (bytes 20-22, x1000)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.hughes_power_watchdog.const import (
    CONF_DUAL_LINE,
    SENSOR_POWER_FACTOR,
    SENSOR_POWER_FACTOR_L2,
)
from custom_components.hughes_power_watchdog.sensor import (
    HughesPowerWatchdogPowerFactorSensor,
    _line_2_sensors,
    async_setup_entry as sensor_setup_entry,
)

from .packets import V1_L1_CAPTURE, V1_L2_CAPTURE, v1_packet


def _feed(coordinator, *packets: bytes) -> None:
    """Deliver V1 packets as two 20-byte BLE chunks each."""
    for packet in packets:
        coordinator._notification_handler_v1(0, bytearray(packet[:20]))
        coordinator._notification_handler_v1(0, bytearray(packet[20:]))


def _apparent_pf(packet: bytes) -> float:
    """Compute P / (V x I) from a captured packet, independent of the parser."""
    volts = int.from_bytes(packet[3:7], "big", signed=True) / 10000
    amps = int.from_bytes(packet[7:11], "big", signed=True) / 10000
    watts = int.from_bytes(packet[11:15], "big", signed=True) / 10000
    return watts / (volts * amps)


async def test_captured_packets_match_computed_power_factor(make_coordinator) -> None:
    """The decoded field agrees with P / (V x I) on real Line 1 and Line 2 packets."""
    coordinator = make_coordinator()
    _feed(coordinator, V1_L1_CAPTURE, V1_L2_CAPTURE)

    assert coordinator.data[SENSOR_POWER_FACTOR] == pytest.approx(0.840)
    assert coordinator.data[SENSOR_POWER_FACTOR_L2] == pytest.approx(0.999)
    assert coordinator.data[SENSOR_POWER_FACTOR] == pytest.approx(
        _apparent_pf(V1_L1_CAPTURE), abs=0.01
    )
    assert coordinator.data[SENSOR_POWER_FACTOR_L2] == pytest.approx(
        _apparent_pf(V1_L2_CAPTURE), abs=0.01
    )


async def test_single_line_power_factor(make_coordinator) -> None:
    """A single-line device reports Line 1 only."""
    coordinator = make_coordinator()
    _feed(coordinator, v1_packet(1, power_factor=950))
    assert coordinator.data[SENSOR_POWER_FACTOR] == pytest.approx(0.95)
    assert SENSOR_POWER_FACTOR_L2 not in coordinator.data


@pytest.mark.parametrize("raw", [0, 1000])
async def test_power_factor_bounds_are_accepted(make_coordinator, raw: int) -> None:
    """0.000 and 1.000 are valid power factors."""
    coordinator = make_coordinator()
    _feed(coordinator, v1_packet(1, power_factor=raw))
    assert coordinator.data[SENSOR_POWER_FACTOR] == pytest.approx(raw / 1000)


@pytest.mark.parametrize("raw", [1001, 5000, 0xFFFFFF])
async def test_out_of_range_power_factor_is_discarded(make_coordinator, raw: int) -> None:
    """Values above 1.0 are not shown, since the field is inferred."""
    coordinator = make_coordinator()
    _feed(coordinator, v1_packet(1, power_factor=raw))
    assert coordinator.data[SENSOR_POWER_FACTOR] is None


async def test_power_factor_does_not_disturb_other_fields(make_coordinator) -> None:
    """Voltage, current, power and energy still decode from the same packets."""
    coordinator = make_coordinator()
    _feed(coordinator, V1_L1_CAPTURE, V1_L2_CAPTURE)
    assert coordinator.data["voltage_line_1"] == pytest.approx(119.7637, abs=1e-4)
    assert coordinator.data["energy_line_1"] == pytest.approx(3898.88)
    assert coordinator.data["energy_line_2"] == pytest.approx(5000.07)


async def test_v1_gets_power_factor_sensors(hass: HomeAssistant, make_coordinator) -> None:
    """V1 devices now get Line 1 and (once dual-line) Line 2 power factor sensors."""
    coordinator = make_coordinator(**{CONF_DUAL_LINE: True})
    hass.data.setdefault("hughes_power_watchdog", {})[
        coordinator.config_entry.entry_id
    ] = coordinator
    added: list = []
    await sensor_setup_entry(hass, coordinator.config_entry, lambda e: added.extend(e))

    pf_types = {
        e._sensor_type for e in added if isinstance(e, HughesPowerWatchdogPowerFactorSensor)
    }
    assert pf_types == {SENSOR_POWER_FACTOR, SENSOR_POWER_FACTOR_L2}


async def test_line_2_sensor_list_includes_power_factor_on_v1(make_coordinator) -> None:
    """The late-added Line 2 sensors include power factor for V1."""
    coordinator = make_coordinator()
    assert not coordinator.is_v2_protocol
    types = {
        e._sensor_type
        for e in _line_2_sensors(coordinator)
        if isinstance(e, HughesPowerWatchdogPowerFactorSensor)
    }
    assert types == {SENSOR_POWER_FACTOR_L2}
