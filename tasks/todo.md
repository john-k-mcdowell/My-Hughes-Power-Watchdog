# Hughes Power Watchdog HA Integration

## Current Status: v0.3.2 - Working

**Tested on:** PWD50-EPO (Gen I) via ESP32 Bluetooth Proxy

---

## Completed Features

### Core Functionality
- [x] HACS-compatible integration structure
- [x] Bluetooth auto-discovery of PMD/PWS devices
- [x] UI-based configuration flow (no YAML needed)
- [x] BLE communication with persistent connection
- [x] Data parsing for 40-byte packets
- [x] ESP32 Bluetooth Proxy support

### Sensors (Working)
- [x] Line 1 Voltage (volts)
- [x] Line 1 Current (amps)
- [x] Line 1 Power (watts)
- [x] Line 2 Voltage (volts) - 50A units
- [x] Line 2 Current (amps) - 50A units
- [x] Line 2 Power (watts) - 50A units
- [x] Total Combined Power (L1 + L2)
- [x] Cumulative Power Usage (kWh)
- [x] Error Code
- [x] Error Description

### Infrastructure
- [x] Persistent BLE connection with idle timeout
- [x] Command queue system (for future two-way communication)
- [x] Connection health monitoring
- [x] Adaptive retry with exponential backoff
- [x] Proper HA entity naming and device classes
- [x] Device registry integration

---

## Future Development

### Not Yet Implemented
- [ ] Monitoring Switch - Enable/disable BLE connection to allow other apps to connect
- [ ] Reset Power Usage Total command
- [ ] Configurable scan interval via options flow
- [ ] Alerts/notifications for error conditions

### Testing Needed
- [ ] Test on PWS (Power Watch) models
- [ ] Test on 30A units (Line 1 only)
- [ ] Test direct Bluetooth connection (without proxy)

---

## Version History

### v0.3.2 (Current)
- Fixed BLE connection warning (use `establish_connection()`)
- Reduced log noise for non-data packets
- Updated README with testing status

### v0.3.1
- Fixed BLE connection and device registry issues

### v0.3.0
- Persistent connection architecture
- Command queue system
- Connection health monitoring

### v0.2.0
- BLE coordinator implementation
- Data parsing for 40-byte packets
- Sensor entities with real data

### v0.1.0
- Initial HACS-compatible structure
- UI-based configuration flow
- Entity definitions (placeholders)

---

## Project Files

```
custom_components/hughes_power_watchdog/
├── __init__.py        # Integration initialization
├── config_flow.py     # UI configuration flow
├── const.py           # Constants and configuration
├── coordinator.py     # BLE data coordinator
├── manifest.json      # Integration metadata (v0.3.2)
├── sensor.py          # Sensor entities
├── strings.json       # UI translations
├── switch.py          # Switch entities (not functional yet)
├── version.py         # Version (0.3.2)
└── translations/
    └── en.json        # English translations
```
