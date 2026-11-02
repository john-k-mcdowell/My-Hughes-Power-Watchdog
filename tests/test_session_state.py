"""Tests for resetting the session state when the BLE connection changes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

COORDINATOR = "custom_components.hughes_power_watchdog.coordinator"


def _stale(coordinator) -> None:
    """Mark the coordinator as if a previous connection was fully set up."""
    coordinator._v2_initialized = True
    coordinator._v2_notifications_active = True
    coordinator._v1_notifications_active = True
    coordinator._time_synced = True


def _assert_reset(coordinator) -> None:
    """Assert all init and subscription flags are cleared."""
    assert coordinator._v2_initialized is False
    assert coordinator._v2_notifications_active is False
    assert coordinator._v1_notifications_active is False
    assert coordinator._time_synced is False


def _fake_client(connected: bool = True) -> MagicMock:
    client = MagicMock()
    client.is_connected = connected
    client.disconnect = AsyncMock()
    client.stop_notify = AsyncMock()
    return client


async def test_reset_session_state(make_coordinator) -> None:
    """The helper clears every flag."""
    coordinator = make_coordinator("WD_V5_000000000000")
    _stale(coordinator)
    coordinator._reset_session_state()
    _assert_reset(coordinator)


async def test_new_connection_resets_stale_state(make_coordinator) -> None:
    """A dropped connection must not leave stale init flags on the next connect."""
    coordinator = make_coordinator("WD_V5_000000000000")
    _stale(coordinator)  # device dropped the link without _disconnect() running
    new_client = _fake_client()

    with (
        patch(f"{COORDINATOR}.bluetooth.async_ble_device_from_address") as device,
        patch(f"{COORDINATOR}.establish_connection", AsyncMock(return_value=new_client)),
    ):
        device.return_value = MagicMock()
        assert await coordinator._ensure_connected() is new_client

    _assert_reset(coordinator)


async def test_existing_connection_keeps_state(make_coordinator) -> None:
    """Reusing a live connection must not reset the init flags."""
    coordinator = make_coordinator("WD_V5_000000000000")
    coordinator._client = _fake_client(connected=True)
    _stale(coordinator)

    assert await coordinator._ensure_connected() is coordinator._client

    assert coordinator._v2_initialized is True
    assert coordinator._v2_notifications_active is True


async def test_disconnect_resets_state(make_coordinator) -> None:
    """A clean disconnect also clears the flags."""
    coordinator = make_coordinator("WD_V5_000000000000")
    coordinator._client = _fake_client()
    _stale(coordinator)

    await coordinator._disconnect()

    assert coordinator._client is None
    _assert_reset(coordinator)
