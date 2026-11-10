"""Tests for dual-line (50A) detection and the energy counters."""

from __future__ import annotations

import struct

import pytest

from custom_components.hughes_power_watchdog.const import (
    CONF_DUAL_LINE,
    SENSOR_ENERGY_L1,
    SENSOR_ENERGY_L2,
    SENSOR_TOTAL_POWER,
    V2_BYTE_ENERGY_START,
    V2_BYTE_VOLTAGE_START,
    V2_DUAL_BLOCK_L2_ENERGY_START,
    V2_DUAL_BLOCK_L2_VOLTAGE_START,
)

from .packets import V2_DUAL_CLOSED, V2_DUAL_OPEN, v1_packet


def _u32(packet: bytes, start: int) -> float:
    """Decode a big-endian uint32 / 10000 field from a captured packet."""
    return struct.unpack(">I", packet[start : start + 4])[0] / 10000


def _feed_v1(coordinator, *packets: bytes) -> None:
    """Deliver V1 packets as two 20-byte BLE chunks each."""
    for packet in packets:
        coordinator._notification_handler_v1(0, bytearray(packet[:20]))
        coordinator._notification_handler_v1(0, bytearray(packet[20:]))


def _with_l2_voltage(packet: bytes, volts: float) -> bytes:
    """Return a copy of a dual-block packet with a different Line 2 voltage."""
    out = bytearray(packet)
    start = V2_DUAL_BLOCK_L2_VOLTAGE_START
    out[start : start + 4] = struct.pack(">I", round(volts * 10000))
    return bytes(out)


# --- V2 captured 50A packets (issue #17) ------------------------------------


async def test_v2_dual_block_detected_and_remembered(make_coordinator) -> None:
    """A dual-block packet marks the device 50A and persists it in the entry."""
    coordinator = make_coordinator("WD_E7_000000000000")
    assert not coordinator.is_dual_line
    assert CONF_DUAL_LINE not in coordinator.config_entry.data

    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))

    assert coordinator.is_dual_line
    assert coordinator.config_entry.data[CONF_DUAL_LINE] is True


async def test_dual_line_remembered_across_restart(make_coordinator) -> None:
    """A device remembered as 50A is dual-line before any packet arrives."""
    coordinator = make_coordinator("WD_E7_000000000000", **{CONF_DUAL_LINE: True})
    assert coordinator.is_dual_line


async def test_v2_per_line_energy_and_total(make_coordinator) -> None:
    """Per-line energy sensors hold each line's counter; the total is their sum."""
    coordinator = make_coordinator("WD_E7_000000000000")
    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))
    data = coordinator.data

    energy_l1 = _u32(V2_DUAL_CLOSED, V2_BYTE_ENERGY_START)
    energy_l2 = _u32(V2_DUAL_CLOSED, V2_DUAL_BLOCK_L2_ENERGY_START)
    assert data[SENSOR_ENERGY_L1] == pytest.approx(energy_l1)
    assert data[SENSOR_ENERGY_L2] == pytest.approx(energy_l2)
    assert data[SENSOR_TOTAL_POWER] == pytest.approx(energy_l1 + energy_l2)


async def test_v2_invalid_line_2_keeps_last_energy(make_coordinator) -> None:
    """A packet with an out-of-range Line 2 block must not drop the total."""
    coordinator = make_coordinator("WD_E7_000000000000")
    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))
    total = coordinator.data[SENSOR_TOTAL_POWER]
    energy_l2 = coordinator.data[SENSOR_ENERGY_L2]

    # Line 2 below the plausibility range (e.g. a voltage sag)
    coordinator._notification_handler_v2(
        0, bytearray(_with_l2_voltage(V2_DUAL_OPEN, 50.0))
    )

    assert coordinator.data[SENSOR_TOTAL_POWER] == pytest.approx(total, abs=0.5)
    assert coordinator.data[SENSOR_ENERGY_L2] == pytest.approx(energy_l2)


async def test_v2_line_1_voltage_parsed(make_coordinator) -> None:
    """Sanity check that the captured packet decodes to its real voltage."""
    coordinator = make_coordinator("WD_E7_000000000000")
    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))
    expected = _u32(V2_DUAL_CLOSED, V2_BYTE_VOLTAGE_START)
    assert 100 < expected < 140
    assert coordinator.data["voltage_line_1"] == pytest.approx(expected)


async def test_total_withheld_until_line_2_known(make_coordinator) -> None:
    """On a remembered 50A device the total is None until Line 2 energy arrives."""
    coordinator = make_coordinator("WD_E7_000000000000", **{CONF_DUAL_LINE: True})
    coordinator._line_1_data = {
        "voltage": 120.0,
        "current": 1.0,
        "power": 120.0,
        "energy": 100.0,
    }
    data = coordinator._build_data_dict()

    assert data[SENSOR_TOTAL_POWER] is None
    assert data[SENSOR_ENERGY_L1] == 100.0
    assert SENSOR_ENERGY_L2 not in data

    coordinator._line_2_energy = 50.0
    data = coordinator._build_data_dict()
    assert data[SENSOR_TOTAL_POWER] == 150.0
    assert data[SENSOR_ENERGY_L2] == 50.0


async def test_single_line_device_has_no_per_line_energy(make_coordinator) -> None:
    """Single-line devices keep only the plain total."""
    coordinator = make_coordinator("WD_V5_000000000000")
    coordinator._line_1_data = {
        "voltage": 120.0,
        "current": 1.0,
        "power": 120.0,
        "energy": 100.0,
    }
    data = coordinator._build_data_dict()

    assert data[SENSOR_TOTAL_POWER] == 100.0
    assert SENSOR_ENERGY_L1 not in data
    assert SENSOR_ENERGY_L2 not in data


async def test_energy_reset_withholds_total(make_coordinator) -> None:
    """After a reset the total waits for Line 2 to report its own reset counter."""
    coordinator = make_coordinator("WD_E7_000000000000")
    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))
    assert coordinator._line_2_energy is not None

    async def ok(*args, **kwargs) -> bool:
        return True

    coordinator._send_v2_command = ok
    assert await coordinator.async_reset_energy() is True
    assert coordinator._line_2_energy is None
    assert coordinator._build_data_dict()[SENSOR_TOTAL_POWER] is None


# --- V1 packets --------------------------------------------------------------


async def test_v1_line_2_packet_marks_dual_line(make_coordinator) -> None:
    """V1 sends the lines separately; a Line 2 packet marks the device 50A."""
    coordinator = make_coordinator()
    _feed_v1(coordinator, v1_packet(1, energy=100.0))
    assert not coordinator.is_dual_line
    assert coordinator.data[SENSOR_TOTAL_POWER] == 100.0

    _feed_v1(coordinator, v1_packet(2, energy=50.0))
    assert coordinator.is_dual_line
    assert coordinator.config_entry.data[CONF_DUAL_LINE] is True
    assert coordinator.data[SENSOR_ENERGY_L1] == 100.0
    assert coordinator.data[SENSOR_ENERGY_L2] == 50.0
    assert coordinator.data[SENSOR_TOTAL_POWER] == 150.0


async def test_v1_total_stays_continuous_when_line_1_arrives_first(
    make_coordinator,
) -> None:
    """After a reconnect Line 1 may arrive first; the total must not drop to L1."""
    coordinator = make_coordinator()
    _feed_v1(coordinator, v1_packet(1, energy=100.0), v1_packet(2, energy=50.0))
    assert coordinator.data[SENSOR_TOTAL_POWER] == 150.0

    # Next cycle: Line 1 first. Line 2 energy is the last known value.
    _feed_v1(coordinator, v1_packet(1, energy=100.1))
    assert coordinator.data[SENSOR_TOTAL_POWER] == pytest.approx(150.1)


async def test_v1_both_lines_in_one_notification(make_coordinator) -> None:
    """Two concatenated 40-byte packets in one notification are both parsed."""
    coordinator = make_coordinator()
    coordinator._notification_handler_v1(
        0, bytearray(v1_packet(1, energy=100.0) + v1_packet(2, energy=50.0))
    )
    assert coordinator.data[SENSOR_TOTAL_POWER] == 150.0


async def test_v2_dual_block_relay_state_from_open_bit(make_coordinator) -> None:
    """On 50A packets bit 0x10 of byte 42 means the relay is open."""
    from custom_components.hughes_power_watchdog.const import SENSOR_RELAY_STATUS

    coordinator = make_coordinator("WD_E7_000000000000")

    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))
    assert coordinator._build_data_dict()[SENSOR_RELAY_STATUS] == 0x00

    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_OPEN))
    assert coordinator._build_data_dict()[SENSOR_RELAY_STATUS] == 0x10

    coordinator._notification_handler_v2(0, bytearray(V2_DUAL_CLOSED))
    assert coordinator._build_data_dict()[SENSOR_RELAY_STATUS] == 0x00
