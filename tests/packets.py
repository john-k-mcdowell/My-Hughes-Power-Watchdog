"""Packet builders and captured packets shared by the tests."""

from __future__ import annotations

import struct

# Real WD_E7 (50A, V2) dual-block packets from issue #17, relay closed and open.
# Byte 42 / 76: 0x00 / 0x01 closed, 0x10 / 0x11 open (bit 0x10 = relay open).
V2_DUAL_CLOSED = bytes.fromhex(
    "2479774001090100440012dad8000015cd00052e19003c8a0c000001ec002f85f7020000"
    "000000177200000013113e000004b70000d6cc007d50780000016c0020d5f30200000000"
    "00177200017121"
)
V2_DUAL_OPEN = bytes.fromhex(
    "2479774001170100440012dbe5000013340003257d003c8a0c00000153002f85f7020000"
    "00000017720010001311200000049700000000007d5078000000000020d5f30200000000"
    "00177300117121"
)


# Real V1 50A (PMD...) packets from a debug log, one per line. Bytes 20-22 are
# 0x000348 (840) on Line 1 and 0x0003e7 (999) on Line 2: P / (V x I) is 0.841
# and 0.999 for the same packets, i.e. power factor x 1000.
V1_L1_CAPTURE = bytes.fromhex(
    "0103200012464500007a3200300f7e0252ec0000000348000842fc00000000000017726ccc000000"
)
V1_L2_CAPTURE = bytes.fromhex(
    "0103200012347e00008da5004201f602faf33c000003e700091783000000000000177207ec010101"
)


def v1_packet(
    line: int,
    *,
    voltage: float = 120.0,
    current: float = 1.0,
    power: float = 120.0,
    energy: float = 10.0,
    error: int = 0,
    frequency: float = 60.0,
    power_factor: int = 0,
) -> bytes:
    """Return a 40-byte V1 data packet for Line 1 or Line 2."""
    packet = bytearray(40)
    packet[0:3] = b"\x01\x03\x20"
    packet[3:7] = struct.pack(">i", round(voltage * 10000))
    packet[7:11] = struct.pack(">i", round(current * 10000))
    packet[11:15] = struct.pack(">i", round(power * 10000))
    packet[15:19] = struct.pack(">i", round(energy * 10000))
    packet[19] = error
    packet[20:23] = power_factor.to_bytes(3, "big")  # power factor x 1000
    packet[31:35] = struct.pack(">i", round(frequency * 100))
    packet[37:40] = b"\x00\x00\x00" if line == 1 else b"\x01\x01\x01"
    return bytes(packet)
