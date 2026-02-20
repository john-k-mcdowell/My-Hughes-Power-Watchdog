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
    # Legacy protocol constants
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
    # Modern V5 protocol constants
    DEVICE_NAME_PREFIXES_MODERN_V5,
    MODERN_V5_SERVICE_UUID,
    MODERN_V5_BYTE_CURRENT_END,
    MODERN_V5_BYTE_CURRENT_START,
    MODERN_V5_BYTE_ENERGY_END,
    MODERN_V5_BYTE_ENERGY_START,
    MODERN_V5_BYTE_L2_CURRENT_END,
    MODERN_V5_BYTE_L2_CURRENT_START,
    MODERN_V5_BYTE_L2_POWER_END,
    MODERN_V5_BYTE_L2_POWER_START,
    MODERN_V5_BYTE_L2_VOLTAGE_END,
    MODERN_V5_BYTE_L2_VOLTAGE_START,
    MODERN_V5_BYTE_MSG_TYPE,
    MODERN_V5_BYTE_POWER_END,
    MODERN_V5_BYTE_POWER_START,
    MODERN_V5_BYTE_VOLTAGE_END,
    MODERN_V5_BYTE_VOLTAGE_START,
    MODERN_V5_CHARACTERISTIC_UUID,
    MODERN_V5_HEADER,
    MODERN_V5_INIT_COMMAND,
    MODERN_V5_MIN_DATA_PACKET_SIZE,
    MODERN_V5_MIN_ENERGY_PACKET_SIZE,
    MODERN_V5_MIN_L2_PACKET_SIZE,
    MODERN_V5_MSG_TYPE_DATA,
    MODERN_V5_VOLTAGE_MIN,
    # Legacy protocol UUIDs
    LEGACY_SERVICE_UUID,
    # Shared constants
    CONNECTION_CHECK_INTERVAL,
    CONNECTION_DELAY_REDUCTION,
    CONNECTION_MAX_ATTEMPTS,
    CONNECTION_MAX_DELAY,
    DATA_COLLECTION_TIMEOUT,
    DATA_CONVERSION_FACTOR,
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
    ERROR_CODES,
)

_LOGGER = logging.getLogger(__name__)



class HughesPowerWatchdogCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage Hughes Power Watchdog data via BLE.

    Both Legacy and V5 devices stream data continuously via BLE
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
        self._is_modern_v5_protocol: bool | None = None
        self._protocol_detected_by_service: bool = False

        # Initial guess based on device name
        if self._detect_modern_v5_by_name(self.device_name):
            self._is_modern_v5_protocol = True
            _LOGGER.info(
                "[%s] Detected modern_V5 protocol for device %s (by name)",
                self.device_name,
                self.address,
            )
        else:
            self._is_modern_v5_protocol = False
            _LOGGER.info(
                "[%s] Detected legacy protocol for device %s (by name)",
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
        self._line_2_data: dict[str, float] | None = None
        self._error_code: int = 0

        # Modern V5 specific: track if initialization command has been sent
        self._modern_v5_initialized: bool = False

        # Persistent subscription tracking (both protocols use push model)
        self._legacy_notifications_active: bool = False
        self._modern_v5_notifications_active: bool = False
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
    def _detect_modern_v5_by_name(device_name: str) -> bool:
        """Detect if device uses modern V5 protocol based on name.

        Args:
            device_name: The device name from Bluetooth advertisement.

        Returns:
            True if device name suggests modern V5 protocol, False otherwise.
        """
        return any(device_name.startswith(prefix) for prefix in DEVICE_NAME_PREFIXES_MODERN_V5)

    async def _detect_protocol_by_service(self, client: BleakClient) -> bool:
        """Detect protocol by probing BLE service UUIDs on the connected device.

        Args:
            client: Connected BleakClient instance.

        Returns:
            True if modern V5 protocol detected, False for legacy.
        """
        try:
            services = client.services
            service_uuids = [str(s.uuid).lower() for s in services]
            _LOGGER.debug(
                "[%s] Available services: %s", self.device_name, service_uuids
            )

            if MODERN_V5_SERVICE_UUID.lower() in service_uuids:
                _LOGGER.info(
                    "[%s] Detected modern_V5 protocol by service UUID",
                    self.device_name,
                )
                return True

            if LEGACY_SERVICE_UUID.lower() in service_uuids:
                _LOGGER.info(
                    "[%s] Detected legacy protocol by service UUID",
                    self.device_name,
                )
                return False

            _LOGGER.warning(
                "[%s] Could not detect protocol by service, "
                "using name-based detection",
                self.device_name,
            )
            return self._detect_modern_v5_by_name(self.device_name)
        except Exception as err:
            _LOGGER.warning(
                "[%s] Error detecting protocol by service: %s",
                self.device_name,
                err,
            )
            return self._detect_modern_v5_by_name(self.device_name)

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
        model = "Power Watchdog V5" if self._is_modern_v5_protocol else "Power Watchdog"
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
    def is_modern_v5_protocol(self) -> bool:
        """Return True if device uses the modern V5 protocol."""
        return self._is_modern_v5_protocol

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
                    if self._legacy_notifications_active:
                        await self._client.stop_notify(CHARACTERISTIC_UUID_TX)
                        _LOGGER.debug("[%s] Unsubscribed from Legacy notifications", self.device_name)
                    elif self._modern_v5_notifications_active:
                        await self._client.stop_notify(MODERN_V5_CHARACTERISTIC_UUID)
                        _LOGGER.debug("[%s] Unsubscribed from V5 notifications", self.device_name)
                except BleakError as err:
                    _LOGGER.debug("[%s] Error unsubscribing: %s (continuing with disconnect)", self.device_name, err)

                try:
                    await self._client.disconnect()
                    _LOGGER.debug("Disconnected from %s", self.address)
                except BleakError as err:
                    _LOGGER.debug("Error disconnecting from %s: %s", self.address, err)
                finally:
                    self._client = None
                    self._modern_v5_initialized = False
                    self._modern_v5_notifications_active = False
                    self._legacy_notifications_active = False

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
                    self._legacy_notifications_active
                    or self._modern_v5_notifications_active
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
            if detected != self._is_modern_v5_protocol:
                _LOGGER.warning(
                    "[%s] Protocol mismatch: name suggested %s, "
                    "service detected %s. Using service detection.",
                    self.device_name,
                    "modern_V5" if self._is_modern_v5_protocol else "legacy",
                    "modern_V5" if detected else "legacy",
                )
                self._is_modern_v5_protocol = detected
            self._protocol_detected_by_service = True

        if self._is_modern_v5_protocol:
            await self._request_device_status_modern_v5()
        else:
            await self._request_device_status_legacy()

    async def _request_device_status_legacy(self) -> None:
        """Ensure Legacy device has an active persistent notification subscription.

        Legacy devices stream data continuously at ~1s intervals. This method
        subscribes once and keeps the subscription active. Data is pushed to
        entities via async_set_updated_data() in the notification handler.
        Called by the connection watchdog to reconnect if needed.
        """
        try:
            client = await self._ensure_connected()

            if not self._legacy_notifications_active:
                self._data_buffer = bytearray()

                _LOGGER.info(
                    "[%s] Legacy: Subscribing to persistent notifications on %s",
                    self.device_name,
                    CHARACTERISTIC_UUID_TX,
                )

                await client.start_notify(
                    CHARACTERISTIC_UUID_TX, self._notification_handler_legacy
                )
                self._legacy_notifications_active = True

                # Wait briefly for initial data
                await asyncio.sleep(DATA_COLLECTION_TIMEOUT)

            self._last_activity_time = time.time()

        except BleakError as err:
            _LOGGER.debug("[%s] Legacy: Error setting up subscription: %s", self.device_name, err)
            self._legacy_notifications_active = False

    async def _request_device_status_modern_v5(self) -> None:
        """Ensure V5 device has an active persistent notification subscription.

        V5 protocol requires an initialization command on first connection,
        then the device streams data continuously. This method subscribes
        once and keeps the subscription active. Data is pushed to entities
        via async_set_updated_data() in the notification handler.
        Called by the connection watchdog to reconnect if needed.
        """
        try:
            client = await self._ensure_connected()

            # Send initialization command if not yet done
            if not self._modern_v5_initialized:
                self._data_buffer = bytearray()
                _LOGGER.debug(
                    "[%s] modern_V5: Sending init command: %s",
                    self.device_name,
                    MODERN_V5_INIT_COMMAND.hex(),
                )
                try:
                    await client.write_gatt_char(
                        MODERN_V5_CHARACTERISTIC_UUID,
                        MODERN_V5_INIT_COMMAND,
                        response=False,
                    )
                    self._modern_v5_initialized = True
                    _LOGGER.info(
                        "[%s] modern_V5: Initialization command sent successfully",
                        self.device_name,
                    )
                except BleakError as err:
                    _LOGGER.error(
                        "[%s] modern_V5: Failed to send init command: %s",
                        self.device_name,
                        err,
                    )
                    raise

            if not self._modern_v5_notifications_active:
                self._data_buffer = bytearray()

                _LOGGER.info(
                    "[%s] modern_V5: Subscribing to persistent notifications on %s",
                    self.device_name,
                    MODERN_V5_CHARACTERISTIC_UUID,
                )

                await client.start_notify(
                    MODERN_V5_CHARACTERISTIC_UUID, self._notification_handler_modern_v5
                )
                self._modern_v5_notifications_active = True

                # Wait briefly for initial data
                await asyncio.sleep(DATA_COLLECTION_TIMEOUT)

            self._last_activity_time = time.time()

        except BleakError as err:
            _LOGGER.debug(
                "[%s] modern_V5: Error setting up subscription: %s",
                self.device_name,
                err,
            )
            self._modern_v5_initialized = False
            self._modern_v5_notifications_active = False

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

            # Return current data (for Legacy, this is continuously
            # updated by the notification handler)
            return self._build_data_dict()

        except BleakError as err:
            raise UpdateFailed(f"BLE communication error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    # =========================================================================
    # LEGACY PROTOCOL HANDLERS (PMD/PWS/PMS)
    # =========================================================================

    def _notification_handler_legacy(self, sender: int, data: bytearray) -> None:
        """Handle BLE notification data from legacy Hughes device.

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
            "[%s] Legacy: Notification #%d (+%.2fs) %d bytes from %s: %s",
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
            self._parse_data_packet_legacy()
            self._data_buffer = bytearray()

            # Push updated data to all entities immediately
            if self._line_1_data:
                self.async_set_updated_data(self._build_data_dict())

    def _parse_data_packet_legacy(self) -> None:
        """Parse complete 40-byte legacy data packet."""
        if len(self._data_buffer) < TOTAL_DATA_SIZE:
            _LOGGER.warning(
                "[%s] Legacy: Incomplete data packet: %d bytes",
                self.device_name,
                len(self._data_buffer),
            )
            return

        # Log complete raw buffer for debugging
        _LOGGER.debug(
            "[%s] Legacy: Complete buffer (%d bytes): %s",
            self.device_name,
            len(self._data_buffer),
            bytes(self._data_buffer).hex(),
        )

        # Verify header - device sends multiple packet types, only process data packets
        header = bytes(self._data_buffer[BYTE_HEADER_START:BYTE_HEADER_END])
        _LOGGER.debug(
            "[%s] Legacy: Header bytes: %s (expected: %s)",
            self.device_name,
            header.hex(),
            HEADER_BYTES.hex(),
        )
        if header != HEADER_BYTES:
            _LOGGER.debug(
                "[%s] Legacy: Skipping non-data packet with header: %s",
                self.device_name,
                header.hex(),
            )
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

        # Log parsed values for debugging
        _LOGGER.debug(
            "[%s] Legacy: Parsed - V=%.2fV I=%.2fA P=%.2fW E=%.2fkWh Err=%d",
            self.device_name,
            voltage,
            current,
            power,
            energy,
            error_code,
        )

        # Identify which line this data is for (bytes 37-39 in chunk 2)
        line_id = bytes(self._data_buffer[BYTE_LINE_ID_START:BYTE_LINE_ID_END])
        _LOGGER.debug(
            "[%s] Legacy: Line ID bytes: %s (Line1=%s, Line2=%s)",
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
            _LOGGER.debug("[%s] Legacy: Line 1 data: %s", self.device_name, self._line_1_data)
        elif line_id == LINE_2_ID:
            self._line_2_data = {
                "voltage": voltage,
                "current": current,
                "power": power,
                "energy": energy,
            }
            _LOGGER.debug("[%s] Legacy: Line 2 data: %s", self.device_name, self._line_2_data)
        else:
            _LOGGER.warning("[%s] Legacy: Unknown line identifier: %s", self.device_name, line_id.hex())

    # =========================================================================
    # MODERN V5 PROTOCOL HANDLERS
    # =========================================================================

    def _notification_handler_modern_v5(self, sender: int, data: bytearray) -> None:
        """Handle BLE notification data from WD_V5 device.

        WD_V5 sends variable-length packets with $yw@ header and q! end marker.
        Each notification is typically a complete packet. After parsing,
        pushes updated data to all entities immediately.
        """
        now = time.time()
        self._notification_count += 1
        interval = now - self._last_notification_time if self._last_notification_time else 0
        self._last_notification_time = now
        self._last_activity_time = now

        _LOGGER.debug(
            "[%s] modern_V5: Notification #%d (+%.2fs) %d bytes from %s: %s",
            self.device_name,
            self._notification_count,
            interval,
            len(data),
            sender,
            data.hex(),
        )

        # WD_V5 typically sends complete packets per notification
        # Parse immediately if we have the header
        if len(data) >= 4 and data[0:4] == MODERN_V5_HEADER:
            self._parse_data_packet_modern_v5(data)
            # Push updated data to all entities immediately
            if self._line_1_data:
                self.async_set_updated_data(self._build_data_dict())
        else:
            # Buffer data if it doesn't start with header (continuation)
            self._data_buffer.extend(data)
            _LOGGER.debug(
                "[%s] modern_V5: Buffered data, total %d bytes",
                self.device_name,
                len(self._data_buffer),
            )

    def _parse_data_packet_modern_v5(self, data: bytes | bytearray) -> None:
        """Parse WD_V5 data packet.

        Packet structure (45 bytes for full data packet):
        - Bytes 0-3: Header "$yw@" (0x24797740)
        - Byte 4: Unknown (0x01)
        - Byte 5: Sequence number
        - Byte 6: Message type (0x01=data, 0x02=status, 0x06=control)
        - Bytes 7-8: Unknown (0x0022)
        - Bytes 9-12: Voltage (BE int32 / 10000)
        - Bytes 13-16: Current (BE int32 / 10000)
        - Bytes 17-20: Power (BE int32 / 10000)
        - Bytes 21+: Additional fields (energy, frequency, etc.)
        - Last 2 bytes: End marker "q!" (0x7121)
        """
        # Verify minimum packet size
        if len(data) < MODERN_V5_MIN_DATA_PACKET_SIZE:
            _LOGGER.debug(
                "[%s] modern_V5: Packet too short (%d bytes), need at least %d",
                self.device_name,
                len(data),
                MODERN_V5_MIN_DATA_PACKET_SIZE,
            )
            return

        # Verify header
        header = bytes(data[0:4])
        if header != MODERN_V5_HEADER:
            _LOGGER.debug(
                "[%s] modern_V5: Invalid header: %s (expected %s)",
                self.device_name,
                header.hex(),
                MODERN_V5_HEADER.hex(),
            )
            return

        # Get message type
        msg_type = data[MODERN_V5_BYTE_MSG_TYPE]
        sequence = data[5]

        _LOGGER.debug(
            "[%s] modern_V5: Packet type=0x%02x seq=%d len=%d",
            self.device_name,
            msg_type,
            sequence,
            len(data),
        )

        # Only parse data packets (type 0x01)
        if msg_type != MODERN_V5_MSG_TYPE_DATA:
            _LOGGER.debug(
                "[%s] modern_V5: Skipping non-data packet (type 0x%02x): %s",
                self.device_name,
                msg_type,
                data.hex(),
            )
            return

        try:
            # Extract voltage (big-endian int32 ÷ 10000)
            voltage_bytes = data[MODERN_V5_BYTE_VOLTAGE_START:MODERN_V5_BYTE_VOLTAGE_END]
            voltage_raw = struct.unpack(">I", voltage_bytes)[0]
            voltage = voltage_raw / DATA_CONVERSION_FACTOR

            # Extract current (big-endian int32 ÷ 10000)
            current_bytes = data[MODERN_V5_BYTE_CURRENT_START:MODERN_V5_BYTE_CURRENT_END]
            current_raw = struct.unpack(">I", current_bytes)[0]
            current = current_raw / DATA_CONVERSION_FACTOR

            # Extract power (big-endian int32 ÷ 10000)
            power_bytes = data[MODERN_V5_BYTE_POWER_START:MODERN_V5_BYTE_POWER_END]
            power_raw = struct.unpack(">I", power_bytes)[0]
            power = power_raw / DATA_CONVERSION_FACTOR

            # Extract energy if packet is long enough (bytes 21-24).
            # Some packet variants omit this field; keep prior values when absent.
            energy: float | None = None
            if len(data) >= MODERN_V5_MIN_ENERGY_PACKET_SIZE:
                energy_bytes = data[MODERN_V5_BYTE_ENERGY_START:MODERN_V5_BYTE_ENERGY_END]
                energy_raw = struct.unpack(">I", energy_bytes)[0]
                energy = energy_raw / DATA_CONVERSION_FACTOR
                _LOGGER.debug(
                    "[%s] modern_V5: Energy raw=%s(%d) = %.2f kWh",
                    self.device_name,
                    energy_bytes.hex(),
                    energy_raw,
                    energy,
                )

            # Log parsed values with raw hex for debugging
            _LOGGER.debug(
                "[%s] modern_V5: Raw values - V=%s(%d) I=%s(%d) P=%s(%d)",
                self.device_name,
                voltage_bytes.hex(),
                voltage_raw,
                current_bytes.hex(),
                current_raw,
                power_bytes.hex(),
                power_raw,
            )

            # Some 50A V5 devices may send line-specific packets reusing the
            # primary V/I/P offsets, with a legacy-style line identifier.
            packet_line_id = bytes(data[37:40]) if len(data) >= 40 else None
            is_line_2_packet = packet_line_id == LINE_2_ID
            is_line_1_packet = packet_line_id == LINE_1_ID

            if is_line_2_packet:
                line_2_energy = energy
                if line_2_energy is None and self._line_2_data:
                    line_2_energy = self._line_2_data.get("energy")
                self._line_2_data = {
                    "voltage": voltage,
                    "current": current,
                    "power": power,
                    "energy": line_2_energy,
                }
                _LOGGER.debug(
                    "[%s] modern_V5: Line 2 packet - V=%.2fV I=%.2fA P=%.2fW E=%s (line-id mode)",
                    self.device_name,
                    voltage,
                    current,
                    power,
                    f"{line_2_energy:.2f}kWh" if line_2_energy is not None else "n/a",
                )
            else:
                line_1_energy = energy
                if line_1_energy is None and self._line_1_data:
                    line_1_energy = self._line_1_data.get("energy")
                self._line_1_data = {
                    "voltage": voltage,
                    "current": current,
                    "power": power,
                    "energy": line_1_energy,
                }
                if is_line_1_packet:
                    _LOGGER.debug(
                        "[%s] modern_V5: Line 1 packet - V=%.2fV I=%.2fA P=%.2fW E=%s (line-id mode)",
                        self.device_name,
                        voltage,
                        current,
                        power,
                        f"{line_1_energy:.2f}kWh" if line_1_energy is not None else "n/a",
                    )
                else:
                    _LOGGER.debug(
                        "[%s] modern_V5: Line 1 - V=%.2fV I=%.2fA P=%.2fW E=%s",
                        self.device_name,
                        voltage,
                        current,
                        power,
                        f"{line_1_energy:.2f}kWh" if line_1_energy is not None else "n/a",
                    )

            # Try to decode embedded Line 2 block (bytes 25-36). This supports
            # devices that report both lines in one frame.
            embedded_line_2 = self._decode_modern_v5_dual_block_line2(data)
            if not embedded_line_2:
                embedded_line_2 = self._decode_modern_v5_embedded_line2(data)
            if embedded_line_2:
                self._line_2_data = embedded_line_2
                _LOGGER.debug(
                    "[%s] modern_V5: Line 2 - V=%.2fV I=%.2fA P=%.2fW (decoded block)",
                    self.device_name,
                    embedded_line_2["voltage"],
                    embedded_line_2["current"],
                    embedded_line_2["power"],
                )

            # Error code not yet decoded for V5
            self._error_code = 0

            _LOGGER.debug("[%s] modern_V5: Line 1 data: %s", self.device_name, self._line_1_data)

        except struct.error as err:
            _LOGGER.error(
                "[%s] modern_V5: Parse error at struct unpack: %s (data: %s)",
                self.device_name,
                err,
                data.hex(),
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "[%s] modern_V5: Unexpected parse error: %s (data: %s)",
                self.device_name,
                err,
                data.hex(),
            )

    def _decode_modern_v5_dual_block_line2(
        self, data: bytes | bytearray
    ) -> dict[str, float | None] | None:
        """Decode Line 2 for 79-byte V5 packets with dual 34-byte data blocks.

        Observed on Gen 2 50A devices:
        - Block 1 starts at byte 9 (Line 1 V/I/P/E)
        - Block 2 starts at byte 43 (Line 2 V/I/P/E)
        """
        # Needs bytes up through 54 for L2 V/I/P extraction.
        if len(data) < 55:
            return None

        # Byte 7-8 appears to be payload length. 0x0044 (68) indicates two
        # 34-byte blocks in the payload, as seen in Gen 2 50A captures.
        if data[7:9] != b"\x00\x44":
            return None

        l2_voltage_bytes = data[43:47]
        l2_current_bytes = data[47:51]
        l2_power_bytes = data[51:55]

        l2_voltage = struct.unpack(">I", l2_voltage_bytes)[0] / DATA_CONVERSION_FACTOR
        l2_current = struct.unpack(">I", l2_current_bytes)[0] / DATA_CONVERSION_FACTOR
        l2_power = struct.unpack(">I", l2_power_bytes)[0] / DATA_CONVERSION_FACTOR

        if not (MODERN_V5_VOLTAGE_MIN <= l2_voltage <= 145.0):
            return None
        if not (0.0 <= l2_current <= 80.0):
            return None
        if not (0.0 <= l2_power <= 20000.0):
            return None

        _LOGGER.debug(
            "[%s] modern_V5: Dual-block L2 raw V=%s I=%s P=%s",
            self.device_name,
            l2_voltage_bytes.hex(),
            l2_current_bytes.hex(),
            l2_power_bytes.hex(),
        )

        return {
            "voltage": l2_voltage,
            "current": l2_current,
            "power": l2_power,
            "energy": None,
        }

    def _decode_modern_v5_embedded_line2(
        self, data: bytes | bytearray
    ) -> dict[str, float | None] | None:
        """Decode Line 2 from bytes 25-36 in V5 packets using robust fallbacks."""
        if len(data) < MODERN_V5_MIN_L2_PACKET_SIZE:
            return None

        l2_voltage_bytes = data[MODERN_V5_BYTE_L2_VOLTAGE_START:MODERN_V5_BYTE_L2_VOLTAGE_END]
        l2_current_bytes = data[MODERN_V5_BYTE_L2_CURRENT_START:MODERN_V5_BYTE_L2_CURRENT_END]
        l2_power_bytes = data[MODERN_V5_BYTE_L2_POWER_START:MODERN_V5_BYTE_L2_POWER_END]

        # Try the known format first, then common fallback encodings.
        # Scale=100 is included because some vendor payloads use centi-units.
        decode_attempts = (
            ("be_10000", "big", DATA_CONVERSION_FACTOR),
            ("le_10000", "little", DATA_CONVERSION_FACTOR),
            ("be_100", "big", 100),
            ("le_100", "little", 100),
        )

        best_result: dict[str, float] | None = None
        best_error = float("inf")

        for mode, byteorder, scale in decode_attempts:
            voltage = int.from_bytes(l2_voltage_bytes, byteorder=byteorder, signed=False) / scale
            current = int.from_bytes(l2_current_bytes, byteorder=byteorder, signed=False) / scale
            power = int.from_bytes(l2_power_bytes, byteorder=byteorder, signed=False) / scale

            # Plausibility checks for RV shore power.
            if not (MODERN_V5_VOLTAGE_MIN <= voltage <= 260.0):
                continue
            if not (0.0 <= current <= 70.0):
                continue
            if not (0.0 <= power <= 15000.0):
                continue

            # Prefer candidates where real power is reasonably close to
            # apparent power, while allowing PF variation and measurement noise.
            apparent_power = voltage * current
            max_reasonable_power = (apparent_power * 1.25) + 250.0
            if power > max_reasonable_power:
                continue

            error = abs(apparent_power - power)
            if best_result is None or error < best_error:
                best_error = error
                best_result = {
                    "voltage": voltage,
                    "current": current,
                    "power": power,
                    "energy": None,
                }
                _LOGGER.debug(
                    "[%s] modern_V5: Embedded L2 candidate %s accepted V=%.2f I=%.2f P=%.2f",
                    self.device_name,
                    mode,
                    voltage,
                    current,
                    power,
                )

        return best_result

    def _build_data_dict(self) -> dict[str, Any]:
        """Build data dictionary for entities."""
        data = {}

        # Line 1 data (always present)
        if self._line_1_data:
            data[SENSOR_VOLTAGE_L1] = self._line_1_data.get("voltage")
            data[SENSOR_CURRENT_L1] = self._line_1_data.get("current")
            data[SENSOR_POWER_L1] = self._line_1_data.get("power")
            total_energy = self._line_1_data.get("energy")
            if self._line_2_data:
                line_2_energy = self._line_2_data.get("energy")
                if total_energy is not None and line_2_energy is not None:
                    total_energy = total_energy + line_2_energy
            data[SENSOR_TOTAL_POWER] = total_energy

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
