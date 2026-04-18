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
    # V1 protocol constants
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
    HEADER_BYTES,
    LINE_1_ID,
    LINE_2_ID,
    TOTAL_DATA_SIZE,
    V1_BYTE_FREQUENCY_START,
    V1_BYTE_FREQUENCY_END,
    # V2 protocol constants
    DEVICE_NAME_PREFIXES_V2,
    V2_SERVICE_UUID,
    V2_BYTE_CURRENT_END,
    V2_BYTE_CURRENT_START,
    V2_BYTE_ENERGY_END,
    V2_BYTE_ENERGY_START,
    V2_BYTE_MSG_TYPE,
    V2_BYTE_POWER_END,
    V2_BYTE_POWER_START,
    V2_BYTE_VOLTAGE_END,
    V2_BYTE_VOLTAGE_START,
    V2_BYTE_OUTPUT_VOLTAGE_START,
    V2_BYTE_OUTPUT_VOLTAGE_END,
    V2_BYTE_NEUTRAL_DETECTION,
    V2_BYTE_BOOST_MODE,
    V2_BYTE_TEMPERATURE,
    V2_BYTE_FREQUENCY_START,
    V2_BYTE_FREQUENCY_END,
    V2_BYTE_ERROR_CODE,
    V2_BYTE_RELAY_STATUS,
    V2_CHARACTERISTIC_UUID,
    V2_HEADER,
    V2_INIT_COMMAND,
    V2_MIN_DATA_PACKET_SIZE,
    V2_MIN_ENERGY_PACKET_SIZE,
    V2_MIN_EXTENDED_PACKET_SIZE,
    V2_MSG_TYPE_DATA,
    V2_VOLTAGE_MAX,
    V2_VOLTAGE_MIN,
    # V2 dual-block constants
    V2_DUAL_BLOCK_L2_VOLTAGE_START,
    V2_DUAL_BLOCK_L2_VOLTAGE_END,
    V2_DUAL_BLOCK_L2_CURRENT_START,
    V2_DUAL_BLOCK_L2_CURRENT_END,
    V2_DUAL_BLOCK_L2_POWER_START,
    V2_DUAL_BLOCK_L2_POWER_END,
    V2_DUAL_BLOCK_L2_ENERGY_START,
    V2_DUAL_BLOCK_L2_ENERGY_END,
    V2_DUAL_BLOCK_L2_OUTPUT_VOLTAGE_START,
    V2_DUAL_BLOCK_L2_OUTPUT_VOLTAGE_END,
    V2_DUAL_BLOCK_L2_NEUTRAL_DETECTION,
    V2_DUAL_BLOCK_L2_BOOST_MODE,
    V2_DUAL_BLOCK_L2_TEMPERATURE,
    V2_DUAL_BLOCK_L2_FREQUENCY_START,
    V2_DUAL_BLOCK_L2_FREQUENCY_END,
    V2_DUAL_BLOCK_L2_ERROR_CODE,
    V2_DUAL_BLOCK_L2_RELAY_STATUS,
    # V1 protocol UUIDs
    LEGACY_SERVICE_UUID,
    # Shared constants
    CONNECTION_CHECK_INTERVAL,
    CONNECTION_DELAY_REDUCTION,
    CONNECTION_MAX_ATTEMPTS,
    CONNECTION_MAX_DELAY,
    DATA_COLLECTION_TIMEOUT,
    DATA_CONVERSION_FACTOR,
    FREQUENCY_CONVERSION_FACTOR,
    DOMAIN,
    NOTIFICATION_STALE_TIMEOUT,
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
    SENSOR_FREQUENCY,
    SENSOR_OUTPUT_VOLTAGE,
    SENSOR_TEMPERATURE,
    SENSOR_RELAY_STATUS,
    SENSOR_BOOST_MODE,
    SENSOR_NEUTRAL_DETECTION,
    ERROR_CODES,
)

_LOGGER = logging.getLogger(__name__)



class HughesPowerWatchdogCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage Hughes Power Watchdog data via BLE.

    Both V1 and V2 devices stream data continuously via BLE
    notifications. The coordinator subscribes once and pushes updates
    to entities in real-time. The update_interval acts as a connection
    watchdog, reconnecting if the subscription drops.
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

        # Protocol detection - initially based on device name, confirmed by service discovery
        self._is_v2_protocol: bool | None = None
        self._protocol_detected_by_service: bool = False

        # Initial guess based on device name
        if self._detect_v2_by_name(self.device_name):
            self._is_v2_protocol = True
            _LOGGER.info(
                "[%s] Detected V2 protocol for device %s (by name prefix)",
                self.device_name,
                self.address,
            )
        else:
            self._is_v2_protocol = False
            _LOGGER.info(
                "[%s] Detected V1 protocol for device %s (by name prefix)",
                self.device_name,
                self.address,
            )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.address}",
            update_interval=timedelta(seconds=CONNECTION_CHECK_INTERVAL),
        )

        # Data buffers
        self._data_buffer: bytearray = bytearray()
        self._line_1_data: dict[str, float] = {}
        self._line_2_data: dict[str, float] = {}
        self._error_code: int = 0
        self._frequency: float | None = None
        self._output_voltage: float | None = None
        self._temperature: int | None = None
        self._relay_status: int | None = None
        self._boost_mode: int | None = None
        self._neutral_detection: int | None = None

        # V2 specific: track if initialization command has been sent
        self._v2_initialized: bool = False

        # Persistent subscription tracking (both protocols use push model)
        self._v1_notifications_active: bool = False
        self._v2_notifications_active: bool = False
        self._notification_count: int = 0
        self._last_notification_time: float = 0

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

        # Monitoring state (for entity availability)
        self._monitoring_enabled: bool = True

        # Start background tasks
        self._start_background_tasks()

    @staticmethod
    def _detect_v2_by_name(device_name: str) -> bool:
        """Detect if device uses V2 protocol based on name.

        Args:
            device_name: The device name from Bluetooth advertisement.

        Returns:
            True if device name suggests V2 protocol, False otherwise.
        """
        matched = None
        for prefix in DEVICE_NAME_PREFIXES_V2:
            if device_name.startswith(prefix):
                matched = prefix
                break
        if matched:
            _LOGGER.debug(
                "Device name '%s' matched V2 prefix '%s'",
                device_name,
                matched,
            )
        return matched is not None

    async def _detect_protocol_by_service(self, client: BleakClient) -> bool:
        """Detect protocol by probing BLE service UUIDs on the connected device.

        Args:
            client: Connected BleakClient instance.

        Returns:
            True if V2 protocol detected, False for V1.
        """
        try:
            services = client.services
            service_uuids = [str(s.uuid).lower() for s in services]
            _LOGGER.debug(
                "[%s] Available services: %s", self.device_name, service_uuids
            )

            if V2_SERVICE_UUID.lower() in service_uuids:
                _LOGGER.info(
                    "[%s] Confirmed V2 protocol by service UUID",
                    self.device_name,
                )
                return True

            if LEGACY_SERVICE_UUID.lower() in service_uuids:
                _LOGGER.info(
                    "[%s] Confirmed V1 protocol by service UUID",
                    self.device_name,
                )
                return False

            _LOGGER.warning(
                "[%s] Could not detect protocol by service, "
                "using name-based detection",
                self.device_name,
            )
            return self._detect_v2_by_name(self.device_name)
        except Exception as err:
            _LOGGER.warning(
                "[%s] Error detecting protocol by service: %s",
                self.device_name,
                err,
            )
            return self._detect_v2_by_name(self.device_name)

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
        model = "Power Watchdog V2" if self._is_v2_protocol else "Power Watchdog"
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=self.device_name,
            manufacturer="Hughes Autoformers",
            model=model,
            connections={(dr.CONNECTION_BLUETOOTH, self.address)},
        )

    @property
    def monitoring_enabled(self) -> bool:
        """Return True if monitoring is enabled."""
        return self._monitoring_enabled

    @property
    def is_v2_protocol(self) -> bool:
        """Return True if device uses the V2 protocol."""
        return self._is_v2_protocol

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
        """Disconnect from BLE device.

        Explicitly unsubscribes from notifications before disconnecting
        to ensure clean teardown of BLE subscriptions.
        """
        async with self._connection_lock:
            if self._client and self._client.is_connected:
                # Explicitly unsubscribe before disconnecting
                try:
                    if self._v1_notifications_active:
                        await self._client.stop_notify(CHARACTERISTIC_UUID_TX)
                        _LOGGER.debug("[%s] Unsubscribed from V1 notifications", self.device_name)
                    elif self._v2_notifications_active:
                        await self._client.stop_notify(V2_CHARACTERISTIC_UUID)
                        _LOGGER.debug("[%s] Unsubscribed from V2 notifications", self.device_name)
                except BleakError as err:
                    _LOGGER.debug("[%s] Error unsubscribing: %s (continuing with disconnect)", self.device_name, err)

                try:
                    await self._client.disconnect()
                    _LOGGER.debug("Disconnected from %s", self.address)
                except BleakError as err:
                    _LOGGER.debug("Error disconnecting from %s: %s", self.address, err)
                finally:
                    self._client = None
                    self._v2_initialized = False
                    self._v2_notifications_active = False
                    self._v1_notifications_active = False

    async def _monitor_connection_health(self) -> None:
        """Monitor connection health and detect stale notifications.

        Runs in background every 30 seconds. If no notifications have
        arrived for NOTIFICATION_STALE_TIMEOUT seconds, disconnects and
        lets the connection watchdog reconnect on next cycle.
        """
        while True:
            try:
                await asyncio.sleep(30)

                # Only check if we expect notifications to be flowing
                notifications_active = (
                    self._v1_notifications_active
                    or self._v2_notifications_active
                )
                if notifications_active and self._last_notification_time:
                    stale_time = time.time() - self._last_notification_time

                    if stale_time > NOTIFICATION_STALE_TIMEOUT:
                        _LOGGER.warning(
                            "[%s] No notifications received for %d seconds, "
                            "reconnecting",
                            self.device_name,
                            int(stale_time),
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
        Routes to appropriate protocol handler based on device type.
        On first connection, probes BLE services to confirm protocol.
        """
        if not self._protocol_detected_by_service:
            client = await self._ensure_connected()
            detected = await self._detect_protocol_by_service(client)
            if detected != self._is_v2_protocol:
                _LOGGER.warning(
                    "[%s] Protocol mismatch: name suggested %s, "
                    "service detected %s. Using service detection.",
                    self.device_name,
                    "V2" if self._is_v2_protocol else "V1",
                    "V2" if detected else "V1",
                )
                self._is_v2_protocol = detected
            self._protocol_detected_by_service = True

        if self._is_v2_protocol:
            await self._request_device_status_v2()
        else:
            await self._request_device_status_v1()

    async def _request_device_status_v1(self) -> None:
        """Ensure V1 device has an active persistent notification subscription.

        V1 devices stream data continuously at ~1s intervals. This method
        subscribes once and keeps the subscription active. Data is pushed to
        entities via async_set_updated_data() in the notification handler.
        Called by the connection watchdog to reconnect if needed.
        """
        try:
            client = await self._ensure_connected()

            if not self._v1_notifications_active:
                self._data_buffer = bytearray()

                _LOGGER.info(
                    "[%s] V1: Subscribing to persistent notifications on %s",
                    self.device_name,
                    CHARACTERISTIC_UUID_TX,
                )

                await client.start_notify(
                    CHARACTERISTIC_UUID_TX, self._notification_handler_v1
                )
                self._v1_notifications_active = True

                # Wait briefly for initial data
                await asyncio.sleep(DATA_COLLECTION_TIMEOUT)

            self._last_activity_time = time.time()

        except BleakError as err:
            _LOGGER.debug("[%s] V1: Error setting up subscription: %s", self.device_name, err)
            self._v1_notifications_active = False

    async def _request_device_status_v2(self) -> None:
        """Ensure V2 device has an active persistent notification subscription.

        V2 protocol requires an initialization command on first connection,
        then the device streams data continuously. This method subscribes
        once and keeps the subscription active. Data is pushed to entities
        via async_set_updated_data() in the notification handler.
        Called by the connection watchdog to reconnect if needed.
        """
        try:
            client = await self._ensure_connected()

            # Send initialization command if not yet done
            if not self._v2_initialized:
                self._data_buffer = bytearray()
                _LOGGER.debug(
                    "[%s] V2: Sending init command: %s",
                    self.device_name,
                    V2_INIT_COMMAND.hex(),
                )
                try:
                    await client.write_gatt_char(
                        V2_CHARACTERISTIC_UUID,
                        V2_INIT_COMMAND,
                        response=False,
                    )
                    self._v2_initialized = True
                    _LOGGER.info(
                        "[%s] V2: Initialization command sent successfully",
                        self.device_name,
                    )
                except BleakError as err:
                    _LOGGER.error(
                        "[%s] V2: Failed to send init command: %s",
                        self.device_name,
                        err,
                    )
                    raise

            if not self._v2_notifications_active:
                self._data_buffer = bytearray()

                _LOGGER.info(
                    "[%s] V2: Subscribing to persistent notifications on %s",
                    self.device_name,
                    V2_CHARACTERISTIC_UUID,
                )

                await client.start_notify(
                    V2_CHARACTERISTIC_UUID, self._notification_handler_v2
                )
                self._v2_notifications_active = True

                # Wait briefly for initial data
                await asyncio.sleep(DATA_COLLECTION_TIMEOUT)

            self._last_activity_time = time.time()

        except BleakError as err:
            _LOGGER.debug(
                "[%s] V2: Error setting up subscription: %s",
                self.device_name,
                err,
            )
            self._v2_initialized = False
            self._v2_notifications_active = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Connection watchdog - ensures subscription is active.

        Real-time data arrives via push notifications in the protocol-
        specific notification handlers. This method only runs on the
        CONNECTION_CHECK_INTERVAL to verify the subscription is still
        active and reconnect if needed.

        Returns:
            Dictionary of current sensor values (cached, updated by push).
        """
        try:
            # Don't reconnect if monitoring was disabled
            if not self._monitoring_enabled:
                _LOGGER.debug("Monitoring disabled, skipping connection check for %s", self.address)
                return self.data or {}

            # Don't interfere if commands are pending
            if not self._command_queue.empty():
                _LOGGER.debug("Commands pending, skipping check for %s", self.address)
                return self.data or {}

            # Ensure subscription/connection is active
            await self._request_device_status()

            # Return current data (continuously updated by the notification handler)
            return self._build_data_dict()

        except BleakError as err:
            raise UpdateFailed(f"BLE communication error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    # =========================================================================
    # V1 PROTOCOL HANDLERS (PMD/PWS/PMS)
    # =========================================================================

    def _notification_handler_v1(self, sender: int, data: bytearray) -> None:
        """Handle BLE notification data from V1 (legacy) Hughes device.

        Device streams data continuously at ~1s intervals. Each cycle
        sends 40 bytes in two 20-byte chunks. After parsing a complete
        packet, pushes updated data to all entities immediately.
        """
        now = time.time()
        self._notification_count += 1
        interval = now - self._last_notification_time if self._last_notification_time else 0
        self._last_notification_time = now
        self._last_activity_time = now

        _LOGGER.debug(
            "[%s] V1: Notification #%d (+%.2fs) %d bytes from %s: %s",
            self.device_name,
            self._notification_count,
            interval,
            len(data),
            sender,
            data.hex(),
        )

        # Append data to buffer
        self._data_buffer.extend(data)

        # Check if we have a complete 40-byte packet
        if len(self._data_buffer) >= TOTAL_DATA_SIZE:
            self._parse_data_packet_v1()
            self._data_buffer = bytearray()

            # Push updated data to all entities immediately
            if self._line_1_data:
                self.async_set_updated_data(self._build_data_dict())

    def _parse_data_packet_v1(self) -> None:
        """Parse complete 40-byte V1 data packet."""
        if len(self._data_buffer) < TOTAL_DATA_SIZE:
            _LOGGER.warning(
                "[%s] V1: Incomplete data packet: %d bytes",
                self.device_name,
                len(self._data_buffer),
            )
            return

        # Log complete raw buffer for debugging
        _LOGGER.debug(
            "[%s] V1: Complete buffer (%d bytes): %s",
            self.device_name,
            len(self._data_buffer),
            bytes(self._data_buffer).hex(),
        )

        # Verify header - device sends multiple packet types, only process data packets
        header = bytes(self._data_buffer[BYTE_HEADER_START:BYTE_HEADER_END])
        _LOGGER.debug(
            "[%s] V1: Header bytes: %s (expected: %s)",
            self.device_name,
            header.hex(),
            HEADER_BYTES.hex(),
        )
        if header != HEADER_BYTES:
            _LOGGER.debug(
                "[%s] V1: Skipping non-data packet with header: %s",
                self.device_name,
                header.hex(),
            )
            return

        # Extract voltage (big-endian int32 / 10000)
        voltage_bytes = self._data_buffer[BYTE_VOLTAGE_START:BYTE_VOLTAGE_END]
        voltage = struct.unpack(">i", voltage_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract current (big-endian int32 / 10000)
        current_bytes = self._data_buffer[BYTE_CURRENT_START:BYTE_CURRENT_END]
        current = struct.unpack(">i", current_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract power (big-endian int32 / 10000)
        power_bytes = self._data_buffer[BYTE_POWER_START:BYTE_POWER_END]
        power = struct.unpack(">i", power_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract cumulative energy (big-endian int32 / 10000)
        energy_bytes = self._data_buffer[BYTE_ENERGY_START:BYTE_ENERGY_END]
        energy = struct.unpack(">i", energy_bytes)[0] / DATA_CONVERSION_FACTOR

        # Extract error code
        error_code = self._data_buffer[BYTE_ERROR_CODE]
        self._error_code = error_code

        # Extract frequency from chunk 2 (bytes 31-34, int32 / 100)
        freq_bytes = self._data_buffer[V1_BYTE_FREQUENCY_START:V1_BYTE_FREQUENCY_END]
        freq_raw = struct.unpack(">i", freq_bytes)[0]
        frequency = freq_raw / FREQUENCY_CONVERSION_FACTOR
        self._frequency = frequency
        _LOGGER.debug(
            "[%s] V1: Frequency raw=%s(%d) = %.2f Hz",
            self.device_name,
            freq_bytes.hex(),
            freq_raw,
            frequency,
        )

        # Log parsed values for debugging
        _LOGGER.debug(
            "[%s] V1: Parsed - V=%.2fV I=%.2fA P=%.2fW E=%.2fkWh Err=%d Freq=%.2fHz",
            self.device_name,
            voltage,
            current,
            power,
            energy,
            error_code,
            frequency,
        )

        # Identify which line this data is for (bytes 37-39 in chunk 2)
        line_id = bytes(self._data_buffer[BYTE_LINE_ID_START:BYTE_LINE_ID_END])
        _LOGGER.debug(
            "[%s] V1: Line ID bytes: %s (Line1=%s, Line2=%s)",
            self.device_name,
            line_id.hex(),
            LINE_1_ID.hex(),
            LINE_2_ID.hex(),
        )

        if line_id == LINE_1_ID:
            self._line_1_data = {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
            }
            _LOGGER.debug("[%s] V1: Line 1 data: %s", self.device_name, self._line_1_data)
        elif line_id == LINE_2_ID:
            self._line_2_data = {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
            }
            _LOGGER.debug("[%s] V1: Line 2 data: %s", self.device_name, self._line_2_data)
        else:
            _LOGGER.warning("[%s] V1: Unknown line identifier: %s", self.device_name, line_id.hex())

    # =========================================================================
    # V2 PROTOCOL HANDLERS
    # =========================================================================

    def _notification_handler_v2(self, sender: int, data: bytearray) -> None:
        """Handle BLE notification data from V2 device.

        V2 sends variable-length packets with $yw@ header and q! end marker.
        Each notification is typically a complete packet. After parsing,
        pushes updated data to all entities immediately.
        """
        now = time.time()
        self._notification_count += 1
        interval = now - self._last_notification_time if self._last_notification_time else 0
        self._last_notification_time = now
        self._last_activity_time = now

        _LOGGER.debug(
            "[%s] V2: Notification #%d (+%.2fs) %d bytes from %s: %s",
            self.device_name,
            self._notification_count,
            interval,
            len(data),
            sender,
            data.hex(),
        )

        # V2 typically sends complete packets per notification
        # Parse immediately if we have the header
        if len(data) >= 4 and data[0:4] == V2_HEADER:
            self._parse_data_packet_v2(data)
            # Push updated data to all entities immediately
            if self._line_1_data:
                self.async_set_updated_data(self._build_data_dict())
        else:
            # Buffer data if it doesn't start with header (continuation)
            self._data_buffer.extend(data)
            _LOGGER.debug(
                "[%s] V2: Buffered data, total %d bytes",
                self.device_name,
                len(self._data_buffer),
            )

    def _parse_data_packet_v2(self, data: bytes | bytearray) -> None:
        """Parse V2 data packet.

        Packet structure:
        - Bytes 0-3: Header "$yw@" (0x24797740)
        - Byte 4: Protocol version (0x01)
        - Byte 5: Sequence number (1-100)
        - Byte 6: Command/message type (0x01=DLReport, 0x02=ErrorReport, 0x06=SetTime)
        - Bytes 7-8: Payload length (big-endian, 0x0022=34 single-block, 0x0044=68 dual-block)
        - Bytes 9-42: Line 1 payload (34 bytes per block)
        - Bytes 43-76: Line 2 payload (dual-block only, 50A devices)
        - Last 2 bytes: End marker "q!" (0x7121)
        """
        # Verify minimum packet size
        if len(data) < V2_MIN_DATA_PACKET_SIZE:
            _LOGGER.debug(
                "[%s] V2: Packet too short (%d bytes), need at least %d",
                self.device_name,
                len(data),
                V2_MIN_DATA_PACKET_SIZE,
            )
            return

        # Verify header
        header = bytes(data[0:4])
        if header != V2_HEADER:
            _LOGGER.debug(
                "[%s] V2: Invalid header: %s (expected %s)",
                self.device_name,
                header.hex(),
                V2_HEADER.hex(),
            )
            return

        # Get message type and sequence
        msg_type = data[V2_BYTE_MSG_TYPE]
        sequence = data[5]

        _LOGGER.debug(
            "[%s] V2: Packet type=0x%02x seq=%d len=%d",
            self.device_name,
            msg_type,
            sequence,
            len(data),
        )

        # Only parse data packets (DLReport, type 0x01)
        if msg_type != V2_MSG_TYPE_DATA:
            _LOGGER.debug(
                "[%s] V2: Skipping non-data packet (type 0x%02x): %s",
                self.device_name,
                msg_type,
                data.hex(),
            )
            return

        try:
            # Extract Line 1 V/I/P (big-endian uint32 / 10000)
            voltage_bytes = data[V2_BYTE_VOLTAGE_START:V2_BYTE_VOLTAGE_END]
            voltage_raw = struct.unpack(">I", voltage_bytes)[0]
            voltage = voltage_raw / DATA_CONVERSION_FACTOR

            current_bytes = data[V2_BYTE_CURRENT_START:V2_BYTE_CURRENT_END]
            current_raw = struct.unpack(">I", current_bytes)[0]
            current = current_raw / DATA_CONVERSION_FACTOR

            power_bytes = data[V2_BYTE_POWER_START:V2_BYTE_POWER_END]
            power_raw = struct.unpack(">I", power_bytes)[0]
            power = power_raw / DATA_CONVERSION_FACTOR

            # Extract energy if packet is long enough (bytes 21-24)
            energy = 0.0
            if len(data) >= V2_MIN_ENERGY_PACKET_SIZE:
                energy_bytes = data[V2_BYTE_ENERGY_START:V2_BYTE_ENERGY_END]
                energy_raw = struct.unpack(">I", energy_bytes)[0]
                energy = energy_raw / DATA_CONVERSION_FACTOR
                _LOGGER.debug(
                    "[%s] V2: Energy raw=%s(%d) = %.2f kWh",
                    self.device_name,
                    energy_bytes.hex(),
                    energy_raw,
                    energy,
                )

            # Log parsed Line 1 values with raw hex
            _LOGGER.debug(
                "[%s] V2: L1 raw V=%s(%d) I=%s(%d) P=%s(%d)",
                self.device_name,
                voltage_bytes.hex(),
                voltage_raw,
                current_bytes.hex(),
                current_raw,
                power_bytes.hex(),
                power_raw,
            )

            # Store Line 1 data
            self._line_1_data = {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
            }

            # Extract extended single-block fields (bytes 25-42) if available
            if len(data) >= V2_MIN_EXTENDED_PACKET_SIZE:
                self._parse_v2_extended_fields(data)

            # Check for dual-block layout (50A devices, payload length 0x0044 = 68 bytes)
            self._line_2_data = None
            if len(data) >= 59 and data[7:9] == b"\x00\x44":
                self._decode_v2_dual_block_line2(data)

            _LOGGER.debug(
                "[%s] V2: Line 1 - V=%.2fV I=%.2fA P=%.2fW E=%.2fkWh",
                self.device_name,
                voltage,
                current,
                power,
                energy,
            )
            _LOGGER.debug("[%s] V2: Line 1 data: %s", self.device_name, self._line_1_data)

        except struct.error as err:
            _LOGGER.error(
                "[%s] V2: Parse error at struct unpack: %s (data: %s)",
                self.device_name,
                err,
                data.hex(),
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "[%s] V2: Unexpected parse error: %s (data: %s)",
                self.device_name,
                err,
                data.hex(),
            )

    def _parse_v2_extended_fields(self, data: bytes | bytearray) -> None:
        """Parse V2 extended fields from single-block payload bytes 25-42.

        These fields are confirmed by the Android app source code.
        Bytes 25-28 (temp1) remain unidentified.
        """
        # Bytes 25-28: temp1 (internal/unknown) - log for analysis
        temp1_bytes = data[25:29]
        temp1_raw = struct.unpack(">I", temp1_bytes)[0]

        # Output voltage (bytes 29-32, uint32 / 10000)
        out_v_bytes = data[V2_BYTE_OUTPUT_VOLTAGE_START:V2_BYTE_OUTPUT_VOLTAGE_END]
        out_v_raw = struct.unpack(">I", out_v_bytes)[0]
        output_voltage = out_v_raw / DATA_CONVERSION_FACTOR
        self._output_voltage = output_voltage

        # Neutral detection status (byte 34, 0x00 = OK)
        neutral_det = data[V2_BYTE_NEUTRAL_DETECTION]
        self._neutral_detection = neutral_det

        # Boost mode (byte 35, 0=off, 1=active)
        boost = data[V2_BYTE_BOOST_MODE]
        self._boost_mode = boost

        # Temperature (byte 36, degrees C)
        temperature = data[V2_BYTE_TEMPERATURE]
        self._temperature = temperature

        # Frequency (bytes 37-40, uint32 / 100)
        freq_bytes = data[V2_BYTE_FREQUENCY_START:V2_BYTE_FREQUENCY_END]
        freq_raw = struct.unpack(">I", freq_bytes)[0]
        frequency = freq_raw / FREQUENCY_CONVERSION_FACTOR
        self._frequency = frequency

        # Error code (byte 41)
        error_code = data[V2_BYTE_ERROR_CODE]
        self._error_code = error_code

        # Relay status (byte 42, 0x00=ON, 0x01 or 0x02=OFF/Error)
        relay_status = data[V2_BYTE_RELAY_STATUS]
        self._relay_status = relay_status

        # Structured debug log for all extended fields
        _LOGGER.debug(
            "[%s] V2: Extended fields - temp1=%s(%d) outV=%s(%.2fV) "
            "backlight=%d neutral=%d boost=%d temp=%d°C "
            "freq=%s(%.2fHz) error=%d relay=0x%02x",
            self.device_name,
            temp1_bytes.hex(),
            temp1_raw,
            out_v_bytes.hex(),
            output_voltage,
            data[33],  # backlight
            neutral_det,
            boost,
            temperature,
            freq_bytes.hex(),
            frequency,
            error_code,
            relay_status,
        )

        # Warn on unexpected values for beta testing
        if temperature > 100:
            _LOGGER.warning(
                "[%s] V2: Unexpected temperature value: %d°C (raw byte 36 = 0x%02x)",
                self.device_name,
                temperature,
                temperature,
            )
        if relay_status not in (0x00, 0x01, 0x02):
            _LOGGER.warning(
                "[%s] V2: Unknown relay status: 0x%02x (expected 0x00/0x01/0x02)",
                self.device_name,
                relay_status,
            )
        if temp1_raw != 0:
            _LOGGER.debug(
                "[%s] V2: temp1 (bytes 25-28) has non-zero value: %s (%d) - field purpose unknown",
                self.device_name,
                temp1_bytes.hex(),
                temp1_raw,
            )

    def _decode_v2_dual_block_line2(
        self, data: bytes | bytearray
    ) -> None:
        """Decode Line 2 for V2 packets with dual 34-byte data blocks.

        Used by Gen 2 50A devices. Payload length 0x0044 (68) indicates
        two 34-byte blocks:
        - Block 1 starts at byte 9 (Line 1 V/I/P/E + extended fields)
        - Block 2 starts at byte 43 (Line 2 V/I/P/E + extended fields)
        """
        l2_voltage_bytes = data[V2_DUAL_BLOCK_L2_VOLTAGE_START:V2_DUAL_BLOCK_L2_VOLTAGE_END]
        l2_current_bytes = data[V2_DUAL_BLOCK_L2_CURRENT_START:V2_DUAL_BLOCK_L2_CURRENT_END]
        l2_power_bytes = data[V2_DUAL_BLOCK_L2_POWER_START:V2_DUAL_BLOCK_L2_POWER_END]
        l2_energy_bytes = data[V2_DUAL_BLOCK_L2_ENERGY_START:V2_DUAL_BLOCK_L2_ENERGY_END]

        l2_voltage = struct.unpack(">I", l2_voltage_bytes)[0] / DATA_CONVERSION_FACTOR
        l2_current = struct.unpack(">I", l2_current_bytes)[0] / DATA_CONVERSION_FACTOR
        l2_power = struct.unpack(">I", l2_power_bytes)[0] / DATA_CONVERSION_FACTOR
        l2_energy = struct.unpack(">I", l2_energy_bytes)[0] / DATA_CONVERSION_FACTOR

        if not (V2_VOLTAGE_MIN <= l2_voltage <= V2_VOLTAGE_MAX):
            _LOGGER.debug(
                "[%s] V2: Dual-block L2 voltage %.2fV out of range, skipping",
                self.device_name,
                l2_voltage,
            )
            return
        if not (0.0 <= l2_current <= 80.0):
            return
        if not (0.0 <= l2_power <= 20000.0):
            return
        if not (0.0 <= l2_energy <= 10_000_000.0):
            return

        _LOGGER.debug(
            "[%s] V2: Dual-block L2 raw V=%s I=%s P=%s E=%s",
            self.device_name,
            l2_voltage_bytes.hex(),
            l2_current_bytes.hex(),
            l2_power_bytes.hex(),
            l2_energy_bytes.hex(),
        )

        self._line_2_data = {
            "voltage": l2_voltage,
            "current": l2_current,
            "power": l2_power,
            "energy": l2_energy,
        }

        _LOGGER.debug(
            "[%s] V2: Line 2 - V=%.2fV I=%.2fA P=%.2fW E=%.2fkWh (dual-block)",
            self.device_name,
            l2_voltage,
            l2_current,
            l2_power,
            l2_energy,
        )

        # Parse Line 2 extended fields if available (bytes 59-76)
        if len(data) >= 77:
            l2_out_v_bytes = data[V2_DUAL_BLOCK_L2_OUTPUT_VOLTAGE_START:V2_DUAL_BLOCK_L2_OUTPUT_VOLTAGE_END]
            l2_out_v = struct.unpack(">I", l2_out_v_bytes)[0] / DATA_CONVERSION_FACTOR
            l2_neutral = data[V2_DUAL_BLOCK_L2_NEUTRAL_DETECTION]
            l2_boost = data[V2_DUAL_BLOCK_L2_BOOST_MODE]
            l2_temp = data[V2_DUAL_BLOCK_L2_TEMPERATURE]
            l2_freq_bytes = data[V2_DUAL_BLOCK_L2_FREQUENCY_START:V2_DUAL_BLOCK_L2_FREQUENCY_END]
            l2_freq = struct.unpack(">I", l2_freq_bytes)[0] / FREQUENCY_CONVERSION_FACTOR
            l2_error = data[V2_DUAL_BLOCK_L2_ERROR_CODE]
            l2_relay = data[V2_DUAL_BLOCK_L2_RELAY_STATUS]

            _LOGGER.debug(
                "[%s] V2: Dual-block L2 extended - outV=%.2fV neutral=%d boost=%d "
                "temp=%d°C freq=%.2fHz error=%d relay=0x%02x",
                self.device_name,
                l2_out_v,
                l2_neutral,
                l2_boost,
                l2_temp,
                l2_freq,
                l2_error,
                l2_relay,
            )

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

        # New sensors
        data[SENSOR_FREQUENCY] = self._frequency
        data[SENSOR_OUTPUT_VOLTAGE] = self._output_voltage
        data[SENSOR_TEMPERATURE] = self._temperature
        data[SENSOR_RELAY_STATUS] = self._relay_status
        data[SENSOR_BOOST_MODE] = self._boost_mode
        data[SENSOR_NEUTRAL_DETECTION] = self._neutral_detection

        _LOGGER.debug("Built data dict: %s", data)
        return data

    def start_monitoring(self) -> None:
        """Start/restart monitoring and background tasks.

        Called when the monitoring switch is turned on to restart
        the command worker and health monitor tasks.
        """
        self._monitoring_enabled = True
        self._start_background_tasks()
        _LOGGER.debug("Monitoring started for %s", self.address)

    async def async_disconnect(self) -> None:
        """Disconnect from device and cleanup background tasks."""
        # Mark monitoring as disabled (sensors become unavailable)
        self._monitoring_enabled = False

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
