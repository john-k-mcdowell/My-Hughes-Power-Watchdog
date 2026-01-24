"""Data coordinator for Hughes Power Watchdog integration."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from datetime import timedelta
from typing import Any, Callable

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BYTE_CURRENT_END,
    BYTE_CURRENT_START,
    BYTE_ENERGY_END,
    BYTE_ENERGY_START,
    BYTE_ERROR_CODE,
    BYTE_HEADER_END,
    BYTE_HEADER_START,
    BYTE_LINE_ID_END,
    BYTE_LINE_ID_START,
    BYTE_POWER_END,
    BYTE_POWER_START,
    BYTE_VOLTAGE_END,
    BYTE_VOLTAGE_START,
    CHARACTERISTIC_UUID_TX,
    CONNECTION_DELAY_REDUCTION,
    CONNECTION_IDLE_TIMEOUT,
    CONNECTION_MAX_ATTEMPTS,
    CONNECTION_MAX_DELAY,
    DATA_COLLECTION_TIMEOUT,
    DATA_CONVERSION_FACTOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HEADER_BYTES,
    LINE_1_ID,
    LINE_2_ID,
    SENSOR_COMBINED_POWER,
    SENSOR_CURRENT_L1,
    SENSOR_CURRENT_L2,
    SENSOR_ERROR_CODE,
    SENSOR_ERROR_TEXT,
    SENSOR_POWER_L1,
    SENSOR_POWER_L2,
    SENSOR_TOTAL_POWER,
    SENSOR_VOLTAGE_L1,
    SENSOR_VOLTAGE_L2,
    TOTAL_DATA_SIZE,
)

_LOGGER = logging.getLogger(__name__)

# Error code mapping (from ESPHome implementation)
ERROR_CODES = {
    0: "No Error",
    1: "Open Ground",
    2: "Reverse Polarity",
    3: "Open Neutral",
    4: "High Voltage",
    5: "Low Voltage",
    6: "High Voltage Surge",
    7: "Frequency Error",
}


class HughesPowerWatchdogCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Hughes Power Watchdog data via BLE.

    Uses persistent BLE connection with command queue for future two-way
    communication support. Connection is maintained with idle timeout and
    automatic reconnection.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.address: str = config_entry.data["address"]
        self.device_name: str = config_entry.title
        self.config_entry = config_entry

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.address}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        # Data buffers
        self._data_buffer: bytearray = bytearray()
        self._line_1_data: dict[str, float] = {}
        self._line_2_data: dict[str, float] = {}
        self._error_code: int = 0

        # Connection management
        self._client: BleakClient | None = None
        self._connection_lock = asyncio.Lock()
        self._last_activity_time: float = 0

        # Command queue for future two-way communication
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._command_worker_task: asyncio.Task | None = None
        self._health_monitor_task: asyncio.Task | None = None

        # Adaptive retry delays
        self._connect_delay: float = 0.0
        self._read_delay: float = 0.0

        # Start background tasks
        self._start_background_tasks()

    def _start_background_tasks(self) -> None:
        """Start background worker tasks."""
        if self._command_worker_task is None or self._command_worker_task.done():
            self._command_worker_task = asyncio.create_task(self._process_commands())
            _LOGGER.debug("Started command worker task for %s", self.address)

        if self._health_monitor_task is None or self._health_monitor_task.done():
            self._health_monitor_task = asyncio.create_task(
                self._monitor_connection_health()
            )
            _LOGGER.debug("Started connection health monitor for %s", self.address)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the Hughes Power Watchdog."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=self.device_name,
            manufacturer="Hughes Autoformers",
            model="Power Watchdog",
            connections={(dr.CONNECTION_BLUETOOTH, self.address)},
        )

    async def _ensure_connected(self) -> BleakClient:
        """Ensure we have an active BLE connection.

        Uses connection lock to prevent multiple simultaneous connection attempts.
        Implements adaptive retry with exponential backoff on failures.

        Returns:
            BleakClient: Connected BLE client.

        Raises:
            UpdateFailed: If connection cannot be established after max attempts.
        """
        async with self._connection_lock:
            # Return existing connection if still valid
            if self._client and self._client.is_connected:
                return self._client

            # Get BLE device from Home Assistant's bluetooth component
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )

            if not ble_device:
                raise UpdateFailed(
                    f"Could not find Hughes Power Watchdog device {self.address}"
                )

            # Try to establish connection with retry logic
            last_error: Exception | None = None
            for attempt in range(CONNECTION_MAX_ATTEMPTS):
                try:
                    _LOGGER.debug(
                        "Attempting connection to %s (attempt %d/%d)",
                        self.address,
                        attempt + 1,
                        CONNECTION_MAX_ATTEMPTS,
                    )

                    # Create and connect client using establish_connection
                    self._client = await establish_connection(
                        BleakClient, ble_device, self.address
                    )

                    # Success - reduce delay for next time
                    self._connect_delay = max(
                        self._connect_delay * CONNECTION_DELAY_REDUCTION, 0
                    )
                    self._last_activity_time = time.time()

                    _LOGGER.debug("Successfully connected to %s", self.address)
                    return self._client

                except BleakError as err:
                    last_error = err
                    _LOGGER.debug(
                        "Connection attempt %d failed: %s",
                        attempt + 1,
                        err,
                    )

                    # Increase delay for next attempt (exponential backoff)
                    if self._connect_delay == 0:
                        self._connect_delay = 1.0
                    else:
                        self._connect_delay = min(
                            self._connect_delay * 2, CONNECTION_MAX_DELAY
                        )

                    # Wait before retry (unless it's the last attempt)
                    if attempt < CONNECTION_MAX_ATTEMPTS - 1:
                        await asyncio.sleep(self._connect_delay)

            # All attempts failed
            raise UpdateFailed(
                f"Failed to connect to {self.address} after {CONNECTION_MAX_ATTEMPTS} attempts: {last_error}"
            )

    async def _disconnect(self) -> None:
        """Disconnect from BLE device."""
        async with self._connection_lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.disconnect()
                    _LOGGER.debug("Disconnected from %s", self.address)
                except BleakError as err:
                    _LOGGER.debug("Error disconnecting from %s: %s", self.address, err)
                finally:
                    self._client = None

    async def _monitor_connection_health(self) -> None:
        """Monitor connection health and disconnect idle connections.

        Runs in background and checks every 30 seconds if the connection
        has been idle for longer than CONNECTION_IDLE_TIMEOUT.
        """
        while True:
            try:
                await asyncio.sleep(30)

                # Check if connection is idle
                if self._client and self._client.is_connected:
                    idle_time = time.time() - self._last_activity_time

                    if idle_time > CONNECTION_IDLE_TIMEOUT:
                        _LOGGER.debug(
                            "Connection to %s idle for %d seconds, disconnecting",
                            self.address,
                            int(idle_time),
                        )
                        await self._disconnect()

            except asyncio.CancelledError:
                _LOGGER.debug("Connection health monitor cancelled for %s", self.address)
                break
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error(
                    "Error in connection health monitor for %s: %s",
                    self.address,
                    err,
                )

    async def _process_commands(self) -> None:
        """Process commands from the command queue.

        Worker task that processes commands sequentially to prevent
        device conflicts. After each command, requests device status
        for responsive UI feedback.
        """
        while True:
            try:
                # Wait for command
                command_func, future = await self._command_queue.get()

                try:
                    # Ensure we're connected
                    client = await self._ensure_connected()

                    # Execute command
                    result = await command_func(client)
                    future.set_result(result)

                    # Immediately request status for UI feedback
                    await self._request_device_status()

                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.error(
                        "Error executing command for %s: %s",
                        self.address,
                        err,
                    )
                    future.set_exception(err)
                finally:
                    self._command_queue.task_done()

            except asyncio.CancelledError:
                _LOGGER.debug("Command worker cancelled for %s", self.address)
                break
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error(
                    "Error in command worker for %s: %s",
                    self.address,
                    err,
                )

    async def execute_command(self, command_func: Callable) -> Any:
        """Queue a command for execution.

        Commands are executed sequentially to prevent device conflicts.

        Args:
            command_func: Async function that takes BleakClient and returns result.

        Returns:
            Result from command execution.
        """
        future: asyncio.Future = asyncio.Future()
        await self._command_queue.put((command_func, future))
        return await future

    async def _request_device_status(self) -> None:
        """Request current status from device.

        Subscribes to TX characteristic to receive device data.
        Called after commands to provide responsive UI feedback.
        """
        try:
            client = await self._ensure_connected()

            # Clear buffer for new data
            self._data_buffer = bytearray()

            # Subscribe to notifications
            await client.start_notify(
                CHARACTERISTIC_UUID_TX, self._notification_handler
            )

            # Wait for device to send data (two 20-byte chunks)
            await asyncio.sleep(DATA_COLLECTION_TIMEOUT)

            # Unsubscribe from notifications
            await client.stop_notify(CHARACTERISTIC_UUID_TX)

            # Update last activity time
            self._last_activity_time = time.time()

        except BleakError as err:
            _LOGGER.debug("Error requesting device status: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Hughes Power Watchdog device.

        Yields to command queue - if commands are pending, returns
        cached data to prioritize command execution.

        Returns:
            Dictionary of sensor values.

        Raises:
            UpdateFailed: If data cannot be retrieved.
        """
        try:
            # Don't poll if commands are pending - let them execute first
            if not self._command_queue.empty():
                _LOGGER.debug("Commands pending, skipping poll for %s", self.address)
                return self.data or {}

            # Request device status
            await self._request_device_status()

            # Return parsed data
            return self._build_data_dict()

        except BleakError as err:
            raise UpdateFailed(f"BLE communication error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle BLE notification data from Hughes device.

        Device sends 40 bytes total in two 20-byte chunks.
        Chunk 1: Header + voltage/current/power/energy/error
        Chunk 2: Line identifier (Line 1 or Line 2)
        """
        _LOGGER.debug("Received %d bytes from characteristic %s", len(data), sender)

        # Append data to buffer
        self._data_buffer.extend(data)

        # Check if we have a complete 40-byte packet
        if len(self._data_buffer) >= TOTAL_DATA_SIZE:
            self._parse_data_packet()
            # Clear buffer after parsing
            self._data_buffer = bytearray()

    def _parse_data_packet(self) -> None:
        """Parse complete 40-byte data packet."""
        if len(self._data_buffer) < TOTAL_DATA_SIZE:
            _LOGGER.warning("Incomplete data packet: %d bytes", len(self._data_buffer))
            return

        # Verify header - device sends multiple packet types, only process data packets
        header = bytes(self._data_buffer[BYTE_HEADER_START:BYTE_HEADER_END])
        if header != HEADER_BYTES:
            _LOGGER.debug("Skipping non-data packet with header: %s", header)
            return

        # Extract voltage (big-endian int32 ÷ 10000)
        voltage_bytes = self._data_buffer[BYTE_VOLTAGE_START:BYTE_VOLTAGE_END]
        voltage = struct.unpack(">i", voltage_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract current (big-endian int32 ÷ 10000)
        current_bytes = self._data_buffer[BYTE_CURRENT_START:BYTE_CURRENT_END]
        current = struct.unpack(">i", current_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract power (big-endian int32 ÷ 10000)
        power_bytes = self._data_buffer[BYTE_POWER_START:BYTE_POWER_END]
        power = struct.unpack(">i", power_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract cumulative energy (big-endian int32 ÷ 10000)
        energy_bytes = self._data_buffer[BYTE_ENERGY_START:BYTE_ENERGY_END]
        energy = struct.unpack(">i", energy_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract error code
        error_code = self._data_buffer[BYTE_ERROR_CODE]
        self._error_code = error_code

        # Identify which line this data is for (bytes 37-39 in chunk 2)
        line_id = bytes(self._data_buffer[BYTE_LINE_ID_START:BYTE_LINE_ID_END])

        if line_id == LINE_1_ID:
            self._line_1_data = {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
            }
            _LOGGER.debug("Line 1 data: %s", self._line_1_data)
        elif line_id == LINE_2_ID:
            self._line_2_data = {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
            }
            _LOGGER.debug("Line 2 data: %s", self._line_2_data)
        else:
            _LOGGER.warning("Unknown line identifier: %s", line_id)

    def _build_data_dict(self) -> dict[str, Any]:
        """Build data dictionary for entities."""
        data = {}

        # Line 1 data (always present)
        if self._line_1_data:
            data[SENSOR_VOLTAGE_L1] = self._line_1_data.get("voltage")
            data[SENSOR_CURRENT_L1] = self._line_1_data.get("current")
            data[SENSOR_POWER_L1] = self._line_1_data.get("power")
            data[SENSOR_TOTAL_POWER] = self._line_1_data.get("energy")

        # Line 2 data (50A units only)
        if self._line_2_data:
            data[SENSOR_VOLTAGE_L2] = self._line_2_data.get("voltage")
            data[SENSOR_CURRENT_L2] = self._line_2_data.get("current")
            data[SENSOR_POWER_L2] = self._line_2_data.get("power")

            # Calculate combined power (Line 1 + Line 2)
            power_l1 = self._line_1_data.get("power", 0)
            power_l2 = self._line_2_data.get("power", 0)
            data[SENSOR_COMBINED_POWER] = power_l1 + power_l2
        else:
            # 30A unit - set Line 2 to None
            data[SENSOR_VOLTAGE_L2] = None
            data[SENSOR_CURRENT_L2] = None
            data[SENSOR_POWER_L2] = None
            # For 30A, combined power = Line 1 power
            data[SENSOR_COMBINED_POWER] = self._line_1_data.get("power")

        # Error information
        data[SENSOR_ERROR_CODE] = self._error_code
        data[SENSOR_ERROR_TEXT] = ERROR_CODES.get(self._error_code, "Unknown Error")

        _LOGGER.debug("Built data dict: %s", data)
        return data

    def start_monitoring(self) -> None:
        """Start/restart monitoring and background tasks.

        Called when the monitoring switch is turned on to restart
        the command worker and health monitor tasks.
        """
        self._start_background_tasks()
        _LOGGER.debug("Monitoring started for %s", self.address)

    async def async_disconnect(self) -> None:
        """Disconnect from device and cleanup background tasks."""
        # Cancel background tasks
        if self._command_worker_task and not self._command_worker_task.done():
            self._command_worker_task.cancel()
            try:
                await self._command_worker_task
            except asyncio.CancelledError:
                pass

        if self._health_monitor_task and not self._health_monitor_task.done():
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass

        # Disconnect from device
        await self._disconnect()
