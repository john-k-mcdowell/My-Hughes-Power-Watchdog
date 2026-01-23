# Persistent Connection Refactor Plan

## Goal
Refactor the Hughes Power Watchdog integration from brief polling connections to persistent connections with command queue support, following the EasyTouchRV pattern.

## Motivation
- Hughes device supports two-way communication
- Future command implementation requires serialized command handling
- Persistent connections provide better responsiveness for command execution
- Eliminates external dependency on bleak-retry-connector

## Changes Required

### 1. Update coordinator.py
**Current**: Brief connections (connect → read → disconnect per poll)
**New**: Persistent connection with health monitoring

Changes:
- Add command queue system using `asyncio.Queue`
- Add `_ensure_connected()` method for connection management
- Add connection health monitoring with 120-second idle timeout
- Add `_process_commands()` worker task
- Implement adaptive retry logic (exponential backoff)
- Remove bleak-retry-connector dependency
- Use HA's bluetooth component directly
- Add connection state tracking
- Polling respects command queue activity

### 2. Update manifest.json
- Remove `"bleak-retry-connector>=3.5.0"` from requirements
- Requirements becomes empty array: `"requirements": []`
- Update version to 0.3.0

### 3. Update version.py
- Change version from "0.2.0" to "0.3.0"

### 4. Update const.py (if needed)
- Add connection timeout constants
- Add retry delay constants
- Add command-related constants (for future use)

### 5. Update __init__.py
- Add proper shutdown handling for command queue
- Ensure connection cleanup on unload

### 6. Update switch.py (optional enhancement)
- Could add connection status indicator
- Keep existing monitoring on/off functionality

### 7. Update how-it-works.md
- Document new connection pattern
- Document command queue architecture
- Document adaptive retry logic
- Document connection health monitoring

## Implementation Details

### Connection Management
```python
class HughesPowerWatchdogCoordinator(DataUpdateCoordinator):
    def __init__(...):
        # Existing code...
        self._client: BleakClient | None = None
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._connection_lock = asyncio.Lock()
        self._last_activity_time: float = 0
        self._health_monitor_task: asyncio.Task | None = None
        self._command_worker_task: asyncio.Task | None = None
        self._connect_delay = 0.0
        self._read_delay = 0.0

    async def _ensure_connected(self) -> BleakClient:
        """Ensure we have an active connection."""
        async with self._connection_lock:
            if self._client and self._client.is_connected:
                return self._client

            # Connection logic with retry
            for attempt in range(3):
                try:
                    device = bluetooth.async_ble_device_from_address(...)
                    self._client = BleakClient(device)
                    await self._client.connect()
                    self._connect_delay = max(self._connect_delay * 0.75, 0)
                    return self._client
                except BleakError:
                    self._connect_delay = min(self._connect_delay * 2 or 1, 6)
                    await asyncio.sleep(self._connect_delay)
```

### Command Queue System
```python
async def _process_commands(self):
    """Worker task to process command queue."""
    while True:
        command_func, future = await self._command_queue.get()
        try:
            client = await self._ensure_connected()
            result = await command_func(client)
            future.set_result(result)
            # Immediately request status for UI feedback
            await self._request_status()
        except Exception as err:
            future.set_exception(err)
        finally:
            self._command_queue.task_done()

async def execute_command(self, command_func):
    """Queue a command for execution."""
    future = asyncio.Future()
    await self._command_queue.put((command_func, future))
    return await future
```

### Connection Health Monitoring
```python
async def _monitor_connection_health(self):
    """Disconnect idle connections after timeout."""
    while True:
        await asyncio.sleep(30)
        if self._client and self._client.is_connected:
            idle_time = time.time() - self._last_activity_time
            if idle_time > 120:  # 2 minutes
                await self._disconnect()
```

### Polling with Queue Awareness
```python
async def _async_update_data(self) -> dict[str, Any]:
    """Fetch data from device, yielding to command queue."""
    # Don't poll if commands are pending
    if not self._command_queue.empty():
        return self.data  # Return cached data

    try:
        client = await self._ensure_connected()
        await client.start_notify(CHARACTERISTIC_UUID_TX, self._notification_handler)
        await asyncio.sleep(3)
        await client.stop_notify(CHARACTERISTIC_UUID_TX)
        self._last_activity_time = time.time()
        return self._build_data_dict()
    except BleakError as err:
        raise UpdateFailed(f"BLE communication error: {err}") from err
```

## Testing Checklist
- [ ] Integration loads successfully
- [ ] Device discovery works
- [ ] Initial connection establishes
- [ ] Data updates every 30 seconds
- [ ] Idle timeout disconnects after 120 seconds
- [ ] Reconnection works after disconnect
- [ ] Monitoring switch still functions
- [ ] All sensors show correct data
- [ ] Connection survives HA restart
- [ ] Unload properly cleans up resources

## Version Changes
- Version: 0.2.0 → 0.3.0
- Reason: Significant architectural change (persistent connections)
- Semantic versioning: Minor version bump (new capability for future commands)

## Benefits
1. **Command Support**: Infrastructure ready for future two-way communication
2. **Better Responsiveness**: Persistent connection eliminates connection overhead
3. **Fewer Dependencies**: Removes bleak-retry-connector requirement
4. **Better Error Handling**: Custom adaptive retry logic
5. **Resource Efficiency**: Intelligent idle timeout management
6. **HA Best Practices**: Uses only HA's bluetooth component

## Risks
1. **Complexity Increase**: More moving parts (queue, health monitor, workers)
2. **Resource Usage**: Persistent connection uses more resources than brief polling
3. **Potential Issues**: Connection state management edge cases

## Mitigation
- Comprehensive error handling throughout
- Proper cleanup in all code paths
- Connection state validation before operations
- Extensive logging for debugging
