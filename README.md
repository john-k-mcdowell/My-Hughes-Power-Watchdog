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
| **Gen 2** | WiFi + Bluetooth | EPOW | `WD_V5_*`, `WD_E5_*`, `WD_V6_*`, `WD_E6_*` | [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) | PWD30EPOW, PWD50-EPOW |

Both generations are portable or hardwired (-H suffix). This integration uses only the BLE connection, even on Gen 2 WiFi models.

## Tested Models

| Model | Generation | Protocol | Known Issues |
|-------|-----------|----------|-------------|
| PWD50-EPD | Gen 1 | V1 | None |
| PWD-VM-30A | Gen 1 | V1 | None |
| PWD30EPOW | Gen 2 | V2 | None |
| PWD50EPOW | Gen 2 | V2 | None |

Please let me know via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues) if you have tested on other models so they can be included in the README.

This integration allows you to monitor your RV's power directly in Home Assistant without needing a special configuration on an ESP32 device. It connects directly to your Hughes Power Watchdog via Bluetooth or ESP-32 Bluetooth Proxy.

Based on the ESPHome implementation by spbrogan, tango2590, and makifoxgirl.

## Features

### Supported Models
- **Gen 1** - Hughes Power Watchdog (PMD/PWS/PMS) - Bluetooth only models
- **Gen 2** - Hughes Power Watchdog (WD_V5/WD_E5/WD_V6/WD_E6) - WiFi + Bluetooth models (v0.5.0+)

### Real-Time Sensor Updates (v0.6.0)

Starting with v0.6.0, the integration uses a **push-based model** for real-time sensor updates. The device streams data continuously via BLE notifications (~1 second intervals), and the integration subscribes once and pushes updates to Home Assistant entities as they arrive. This replaces the previous polling model that only captured data every 30 seconds.

> **Note:** The real-time push model has been validated on both Gen 1 and Gen 2 devices. If you encounter issues with a specific model, please enable debug logging and report any issues via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).

### Available Sensors

**All Models:**
- **Line 1 Voltage** (volts)
- **Line 1 Current** (amps)
- **Line 1 Power** (watts)
- **Cumulative Power Usage** (kWh)
- **Error Code** (number)
- **Error Description** (text)
- **Frequency Line 1** (Hz) - AC power line frequency

**Gen 2 (V2) Booster Models Only (V8/V9/E8/E9) — _untested_:**
- **Output Voltage** (volts) - Voltage after autoformer adjustment (field mirrors the energy counter on non-booster V5/E5/V6/E6 devices, so it is hidden there)
- **Temperature** (°C) - Device temperature (reads zero on non-booster models)
- **Boost Mode** - Whether the autoformer boost is active (binary sensor)

> These three sensors are only created for V8/V9/E8/E9 models and have **not yet been validated** on hardware. Please report results via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).

**Gen 2 (V2) Models Only:**
- **Relay Status** - Whether the power relay is ON or tripped (binary sensor)
- **Neutral Detection** - Ground/neutral monitoring status (binary sensor)

**50 Amp (Dual-Line) Units Only:**
- **Line 2 Voltage** (volts)
- **Line 2 Current** (amps)
- **Line 2 Power** (watts)
- **Total Combined Power** (L1 + L2, watts)
- **Frequency Line 2** (Hz) - AC power line frequency for Line 2 (Gen 2 V2 only)

### Device Controls (v0.8.0)

> **Gen 1 (V1) device commands are a work in progress.** BLE writes succeed but the device currently ignores them, so command entities (Power Relay, Backlight, Reset Energy, Clear Error History) are **only exposed on Gen 2 (V2) devices** until the V1 wire format is reverse-engineered. The underlying code remains in the codebase.

**Gen 2 (V2) devices:**
- **Power Relay** (switch) - Turn the power relay on/off.
- **Backlight** (light with brightness) - Control the device LED brightness (levels 0-5; HA brightness 0-255 is mapped to the nearest discrete level).
- **Reset Energy Counter** (button) - Reset the cumulative kWh counter to zero.
- **Clear Error History** (button) - Delete all stored error records from the device.
- **Neutral Detection Control** (switch) - Enable/disable ground/neutral monitoring on the device. _Untested — please report results._
- **Auto Clock Sync** - The device clock is automatically synchronized to your HA system time on each BLE connection.

**All devices:**
- **Monitoring Switch** - Enable/disable the BLE connection. Turning monitoring off cleanly unsubscribes from notifications and disconnects, freeing the BLE connection slot (useful for ESPHome Bluetooth Proxy users with the default 3-slot limit). Turning it back on reconnects and resumes real-time data.

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

1. Go to **Settings** -> **Devices & Services**
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

## Gen 2 (V2) Protocol Support

Starting with v0.5.0, this integration supports Gen 2 devices (WiFi + Bluetooth models with device names starting with `WD_V5_`, `WD_E5_`, `WD_V6_`, or `WD_E6_`, such as PWD30EPOW/PWD50EPOW). These devices use a different BLE protocol than the Gen 1 Bluetooth-only models. The protocol header `$yw@` corresponds to the "yw" identifier used in the official [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) app.

**Gen 2 (V2) Status:**
- Voltage, Current, Power readings - Working
- Energy (kWh) - Working
- Real-time push updates (v0.6.0) - Working
- Error codes - Working (v0.7.0)
- Frequency - Working (v0.7.0)
- Line 2 (50A dual-phase) - Working
- Relay Status, Neutral Detection - Working (v0.7.0)
- Device commands — relay, backlight, energy reset, error delete, clock sync - Working (v0.8.0)
- Output Voltage, Temperature, Boost Mode (booster models V8/V9/E8/E9 only) - **Untested**
- Neutral Detection Control switch - **Untested**

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

Then check your Home Assistant logs for entries prefixed with `[V2]` or `[V1]`.

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

V1/V2 protocol documentation reverse-engineered from the Android app source by:
- [gearhead765](https://github.com/gearhead765)

Additional protocol details cross-referenced against the independent [TechBlueprints/dbus-power-watchdog](https://github.com/TechBlueprints/dbus-power-watchdog) Venus OS D-Bus service, which clarified the booster-model gating for V2 output voltage, temperature, and boost mode. See [docs/protocol.md](docs/protocol.md) for details.

### Contributors
- [IAmTheMitchell](https://github.com/IAmTheMitchell) — Gen 2 WD_E5 device support, V2 50A Line 2 sensor fix, protocol documentation for dual-block packet format
- [gearhead765](https://github.com/gearhead765) — Error Log feature and testing (v0.9.0)

## License

MIT License

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).
