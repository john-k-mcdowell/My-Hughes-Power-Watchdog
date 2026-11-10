"""Fake BLE objects shared by the tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE2 = "0000ffe2-0000-1000-8000-00805f9b34fb"
FFF5 = "0000fff5-0000-1000-8000-00805f9b34fb"


def fake_v1_client(properties: list[str], service_uuid: str = FFE0) -> MagicMock:
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

