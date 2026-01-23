# BLE Coordinator Implementation Plan

## Goal
Create a coordinator class to handle BLE communication with the Hughes Power Watchdog device, including connection management, data parsing, and state updates.

## Todo Items

### Phase 1: Create Coordinator File
- [ ] Create coordinator.py with basic structure
- [ ] Define HughesPowerWatchdogCoordinator class
- [ ] Implement initialization and setup methods
- [ ] Add BLE device connection management

### Phase 2: BLE Communication
- [ ] Implement BLE client connection
- [ ] Subscribe to TX characteristic notifications
- [ ] Implement notification callback handler
- [ ] Handle two-chunk data buffering
- [ ] Parse 40-byte data packets

### Phase 3: Data Parsing
- [ ] Extract voltage, current, power from chunks
- [ ] Extract cumulative energy
- [ ] Extract error codes
- [ ] Identify Line 1 vs Line 2 data
- [ ] Calculate combined power for 50A units
- [ ] Convert big-endian int32 values

### Phase 4: Integration Updates
- [ ] Update __init__.py to create coordinator instance
- [ ] Update sensor.py to use coordinator data
- [ ] Update switch.py to control coordinator connection
- [ ] Add error handling and reconnection logic

### Phase 5: Testing & Validation
- [ ] Pre-compile Python code for syntax checking
- [ ] Update how-it-works.md documentation
- [ ] Update version number to 0.2.0
- [ ] Test code structure (no hardware needed yet)

## Technical Approach

### Coordinator Class Design
- Inherit from Home Assistant's `DataUpdateCoordinator`
- Use `bleak` library for BLE communication
- Implement async methods for connection lifecycle
- Buffer chunks and parse complete 40-byte packets
- Store parsed data in coordinator.data dictionary

### Data Structure
```python
coordinator.data = {
    "voltage_line_1": float,
    "current_line_1": float,
    "power_line_1": float,
    "voltage_line_2": float,  # None for 30A units
    "current_line_2": float,  # None for 30A units
    "power_line_2": float,    # None for 30A units
    "combined_power": float,
    "total_power": float,     # Cumulative kWh
    "error_code": int,
    "error_text": str,
}
```

### BLE Protocol Implementation
1. Connect to device using MAC address
2. Subscribe to TX characteristic (0000ffe2...)
3. Receive 20-byte chunk 1 (header + Line data)
4. Buffer chunk 1
5. Receive 20-byte chunk 2 (line identifier)
6. Parse complete 40-byte packet
7. Update coordinator data
8. Trigger entity updates

## Key Considerations
- Keep implementation simple and modular
- Handle both 30A (single line) and 50A (dual line) devices
- Graceful error handling for BLE disconnections
- Efficient data parsing with minimal overhead
- Thread-safe data access

## Files to Modify
1. Create: `custom_components/hughes_power_watchdog/coordinator.py`
2. Update: `custom_components/hughes_power_watchdog/__init__.py`
3. Update: `custom_components/hughes_power_watchdog/sensor.py`
4. Update: `custom_components/hughes_power_watchdog/switch.py`
5. Update: `custom_components/hughes_power_watchdog/version.py` (0.1.0 → 0.2.0)
6. Update: `how-it-works.md`

## Success Criteria
- Coordinator class compiles without syntax errors
- Clean separation of concerns (coordinator handles BLE, entities display data)
- Data structure matches sensor entity expectations
- Code follows Home Assistant best practices
- Documentation is complete and accurate
