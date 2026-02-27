# Hughes Power Watchdog

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/john-k-mcdowell/My-Hughes-Power-Watchdog?include_prereleases)](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/releases)
[![License](https://img.shields.io/github/license/john-k-mcdowell/My-Hughes-Power-Watchdog)](LICENSE)

A Home Assistant custom integration for **Hughes Power Watchdog Surge Protectors** with Bluetooth connectivity.

> **100% Local Control** - This integration communicates directly with the Power Watchdog over Bluetooth Low Energy (BLE). No cloud services, no internet connection required, no data leaves your home.

## Device Generations

Hughes Power Watchdog devices come in two generations, each using a different BLE protocol:

| Generation | Connectivity | Model Suffix | BLE Device Name | Mobile App | Example Models |
|-----------|-------------|-------------|----------------|-----------|---------------|
| **Gen 1** | Bluetooth only | EPO | `PMD*`, `PWS*`, `PMS*` | [Power Watchdog Bluetooth ONLY](https://play.google.com/store/apps/details?id=com.hughes.epo) | PWD30-EPO, PWD50-EPO, PWD50-EPD |
| **Gen 2** | WiFi + Bluetooth | EPOW | `WD_V5_*`, `WD_E5_*` | [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) | PWD30EPOW, PWD50-EPOW |

Both generations are portable or hardwired (-H suffix). This integration uses only the BLE connection, even on Gen 2 WiFi models.

## Tested Models

| Model | Generation | Protocol | Known Issues |
|-------|-----------|----------|-------------|
| PWD50-EPD | Gen 1 | Legacy | None |
| PWD-VM-30A | Gen 1 | Legacy | None |
| PWD30EPOW | Gen 2 | V5 | None |
| PWD50EPOW | Gen 2 | V5 | None |

Please let me know via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues) if you have tested on other models so they can be included in the README.

This integration allows you to monitor your RV's power directly in Home Assistant without needing a special configuration on an ESP32 device. It connects directly to your Hughes Power Watchdog via Bluetooth or ESP-32 Bluetooth Proxy.

Based on the ESPHome implementation by spbrogan, tango2590, and makifoxgirl.

## Features

### Supported Models
- **Gen 1** - Hughes Power Watchdog (PMD/PWS/PMS) - Bluetooth only models
- **Gen 2** - Hughes Power Watchdog (WD_V5/WD_E5) - WiFi + Bluetooth models (v0.5.0+)

### Real-Time Sensor Updates (v0.6.0)

Starting with v0.6.0, the integration uses a **push-based model** for real-time sensor updates. The device streams data continuously via BLE notifications (~1 second intervals), and the integration subscribes once and pushes updates to Home Assistant entities as they arrive. This replaces the previous polling model that only captured data every 30 seconds.

> **Note:** The real-time push model has been validated on both Gen 1 and Gen 2 devices. If you encounter issues with a specific model, please enable debug logging and report any issues via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).

### Available Sensors
- **Line 1 Voltage** (volts)
- **Line 1 Current** (amps)
- **Line 1 Power** (watts)
- **Cumulative Power Usage** (kWh)
- **Error Code** (number)
- **Error Description** (text)

**50 Amp Units Only:**
- **Line 2 Voltage** (volts)
- **Line 2 Current** (amps)
- **Line 2 Power** (watts)
- **Total Combined Power** (L1 + L2, watts)

### Controls
- **Monitoring Switch** - Enable/disable the BLE connection. Turning monitoring off cleanly unsubscribes from notifications and disconnects, freeing the BLE connection slot (useful for ESPHome Bluetooth Proxy users with the default 3-slot limit). Turning it back on reconnects and resumes real-time data.
- *Not Implemented yet* - Reset Power Usage Total

## Installation

### HACS Installation (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog`
6. Select category: "Integration"
7. Click "Add"
8. Find "Hughes Power Watchdog" in the integration list
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/hughes_power_watchdog` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### Automatic Discovery (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Hughes Power Watchdog"
4. Follow the configuration prompts
5. The integration will automatically discover nearby Hughes devices
6. Select your device from the list

### Manual Configuration

If your device is not auto-discovered but is powered on and within Bluetooth range:

1. Follow the steps above - when no devices are found, you'll be prompted for manual entry
2. Enter the MAC address of your Hughes device (found in the Hughes mobile app or your Bluetooth settings)
3. The integration will validate that the device is advertising and configure it

> **Important:** If you successfully configure your device using manual MAC entry, please [open a GitHub issue](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues) and include your device model name. This helps us add it to the auto-discovery list for future users.

## Gen 2 (V5) Protocol Support

Starting with v0.5.0, this integration supports Gen 2 devices (WiFi + Bluetooth models with device names starting with `WD_V5_` or `WD_E5_`, such as PWD30EPOW/PWD50EPOW). These devices use a different BLE protocol than the Gen 1 Bluetooth-only models. The protocol header `$yw@` corresponds to the "yw" identifier used in the official [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) app.

**Gen 2 (V5) Status:**
- Voltage, Current, Power readings - Working
- Energy (kWh) - Working
- Real-time push updates (v0.6.0) - Working
- Error codes - Not yet implemented
- Line 2 (50A dual-phase) - Working

**If you have a Gen 2 device**, please help us by:
1. Enabling debug logging (see below)
2. Checking if the readings match your Hughes mobile app
3. Reporting any issues via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues)

### Debug Logging

Add this to your `configuration.yaml` to enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.hughes_power_watchdog: debug
```

Then check your Home Assistant logs for entries prefixed with `[modern_V5]` or `[Legacy]`.

## Requirements

- Home Assistant 2023.1.0 or newer
- Bluetooth adapter/proxy in range of your Hughes Power Watchdog
- Hughes Power Watchdog with Bluetooth (Gen 1 or Gen 2)

## Troubleshooting

### Device Not Found
- Ensure no other devices are connected to your Hughes Power Watchdog (it only supports one connection at a time)
- Make sure Bluetooth is enabled on your Home Assistant host
- Verify your Hughes device is powered on and within Bluetooth range
- Try using the Hughes mobile app to confirm the device is functioning

### Connection Issues
- Disconnect any mobile apps connected to the Hughes device
- Toggle the Monitoring Switch off and on
- Restart the integration

## Credits

Based on the original ESPHome implementation by:
- [spbrogan](https://github.com/spbrogan)
- [makifoxgirl](https://github.com/makifoxgirl)
- [tango2590](https://github.com/tango2590/Hughes-Power-Watchdog)
- SergeantBort

## License

MIT License

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).
