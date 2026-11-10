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
| **Gen 2** | WiFi + Bluetooth | EPOW | `WD_V5_*`, `WD_E5_*`, `WD_V6_*`, `WD_E6_*`, `WD_E7_*`, `WD_V7_*` | [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) | PWD30EPOW, PWD50-EPOW, PWD50EPOHW, PWD30EPOHW |

Both generations are portable or hardwired (-H suffix). This integration uses only the BLE connection, even on Gen 2 WiFi models.

## Tested Models

| Model | Generation | Protocol | Known Issues |
|-------|-----------|----------|-------------|
| PWD50-EPD | Gen 1 | V1 | None |
| PWD-VM-30A | Gen 1 | V1 | None |
| PWD30EPOW | Gen 2 | V2 | None |
| PWD50EPOW | Gen 2 | V2 | None |
| PWD50EPOHW, PWD30EPOHW | Gen 2 | V2 | None |

Please let me know via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues) if you have tested on other models so they can be included in the README.

This integration allows you to monitor your RV's power directly in Home Assistant without needing a special configuration on an ESP32 device. It connects directly to your Hughes Power Watchdog via Bluetooth or ESP-32 Bluetooth Proxy.

Based on the ESPHome implementation by spbrogan, tango2590, and makifoxgirl.

## Features

### Supported Models
- **Gen 1** - Hughes Power Watchdog (PMD/PWS/PMS) - Bluetooth only models
- **Gen 2** - Hughes Power Watchdog (WD_V5/WD_E5/WD_V6/WD_E6/WD_E7/WD_V7) - WiFi + Bluetooth models (v0.5.0+)

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
- **Power Factor** (per line) - Ratio of real to apparent power. Gen 2 devices report it directly. On Gen 1 it is decoded from bytes 20-22 of the data packets; verified on a Gen 1 50A device, where it matches P / (V × I), but not yet on other Gen 1 models (values outside 0-1 are ignored)

**Gen 2 (V2) Booster Models Only (V8/V9/E8/E9) — _untested_:**
- **Output Voltage** (volts) - Voltage after autoformer adjustment (field mirrors the energy counter on non-booster V5/E5/V6/E6 devices, so it is hidden there)
- **Temperature** (°C) - Device temperature (reads zero on non-booster models)
- **Boost Mode** - Whether the autoformer boost is active (binary sensor)

> These three sensors are only created for V8/V9/E8/E9 models and have **not yet been validated** on hardware. Please report results via [GitHub issues](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).

**Gen 2 (V2) Models Only:**
- **Relay Status** - Whether the power relay is ON or tripped (binary sensor). On 50A (dual-line) devices this is experimental: it reads the relay-open bit seen for a commanded open on a WD_E7 and WD_E5, and it is not yet known whether it also shows a trip or the power-up delay. See note below.
- **Neutral Detection** - Whether a lost-neutral fault (error code 8) is currently reported (binary sensor)

**50 Amp (Dual-Line) Units Only:**
- **Line 2 Voltage** (volts)
- **Line 2 Current** (amps)
- **Line 2 Power** (watts)
- **Total Combined Power** (L1 + L2, watts)
- **Energy Line 1** / **Energy Line 2** (kWh) - The device's per-line energy counters. Unlike integrating the power sensors in Home Assistant, they include usage while the device was disconnected from Home Assistant
- **Frequency Line 2** (Hz) - AC power line frequency for Line 2 (Gen 2 V2 only)

### Device Controls (v0.8.0)

> **Gen 1 (V1) device commands are a work in progress.** BLE writes succeed but the device currently ignores them, so the Power Relay switch and Clear Error History button are **only exposed on Gen 2 (V2) devices** until their V1 wire formats are verified. Restart After Trip and Reset Energy Counter are exposed on Gen 1 (see below). The underlying code remains in the codebase. The one exception is **Restart After Trip** (below), whose wire format is known and tested.

**Gen 1 (V1) devices:**
- **Restart After Trip** (button) - Restores power after the Watchdog trips on an over-current (E3/E4) or missing-neutral (E8) error, the same as the restart button on the official Gen 1 app's alert screen. Pressing it when no E3/E4/E8 error is active is refused and nothing is sent to the device. The button's attributes show when the command was last sent (`last_sent`) and the device's acknowledgment (`last_reply`, normally `relay on`, and `last_reply_time`). Clear the cause of the trip (reduce the load) before pressing it.

> **Tested on Gen 1 30A only.** The Restart After Trip button has been verified on a Gen 1 30A device, but **not on a Gen 1 50A (dual-line) device**. 50A devices report each line separately, so behavior on a real E3/E4/E8 trip may differ. **If you use this button on a Gen 1 50A device, please report whether it worked or not on [issue #25](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues/25).** Include the error (E3, E4 or E8), whether power was restored, and the button's `last_reply` attribute. Please don't force a trip just to test it.

- **Reset Energy Counter** (button) - Zeroes the device's cumulative kWh counter using the real command from the official Gen 1 app. **This cannot be undone.** Verified on a Gen 1 50A device: the device replies `RESET` and **both lines** reset to zero. The button's attributes show the last command sent and the device's reply (`last_reply`). Add a confirmation to your dashboard card if you want protection against accidental presses.
- **Backlight:** not available on Gen 1, see the note below.

> **No Gen 1 backlight control (so far).** A Gen 1 50A device (BLE name `PMD…`) did not respond to the official app's backlight command in either form we tried (the level as an ASCII digit, and as a raw byte): no reply and no change. Its official iOS app has no backlight setting either, so that model most likely has no software-controllable backlight, and the integration no longer creates a Gen 1 Backlight light. The Gen 1 backlight code is kept, disabled by `V1_BACKLIGHT_ENTITY_ENABLED` in `const.py`. If your Gen 1 device's official app **does** have a backlight setting and you would like to help test it, please [open an issue](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues/new) with your model name.

**Gen 2 (V2) devices:**
- **Power Relay** (switch) - Turn the power relay on/off. On 30A (single-line) devices the on/off indicator reflects real relay state. On 50A (dual-line) devices the indicator is experimental (it follows the relay-open bit seen for a commanded open on a WD_E7 and WD_E5). The commands work on both.
- **Backlight** (light with brightness) - Control the device LED brightness (levels 0-5; HA brightness 0-255 is mapped to the nearest discrete level).
- **Reset Energy Counter** (button) - Reset the cumulative kWh counter to zero.
- **Clear Error History** (button) - Delete all stored error records from the device.
- **Neutral Detection Control** (switch) - Enable/disable ground/neutral monitoring on the device. Reflects the device's real monitoring-enabled/bypassed state.
- **Auto Clock Sync** - The device clock is automatically synchronized to your HA system time on each BLE connection.

**All devices:**
- **Monitoring Switch** - Enable/disable the BLE connection. Turning monitoring off cleanly unsubscribes from notifications and disconnects, freeing the BLE connection slot (useful for ESPHome Bluetooth Proxy users with the default 3-slot limit). Turning it back on reconnects and resumes real-time data.

## Installation

Home Assistant **2026.11** moved HACS into Home Assistant itself as the built-in **Marketplace** (see the [2026.11 release notes](https://www.home-assistant.io/blog/2026/11/04/release-202611/) and the [Marketplace documentation](https://www.home-assistant.io/integrations/marketplace/)). Follow the section that matches your Home Assistant version. This integration still requires Home Assistant **2024.11.0** or newer.

### Marketplace Installation (Home Assistant 2026.11 and newer)

1. Open **Settings > Marketplace**. The first time, select "I understand the risks and agree."
2. In the upper-right corner, select **Add from link**.
3. Under "GitHub link", enter `https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog` (or `john-k-mcdowell/My-Hughes-Power-Watchdog`). If asked for a type, choose **Integration**, then select **Add**. Adding a custom repository needs a connected GitHub account; if prompted, select **Continue**, open the link, enter the code and approve.
4. Open "Hughes Power Watchdog" in the Marketplace and select **Install**, review the version, and select **Install** again.
5. If the setup page doesn't open on its own, add the integration under **Settings > Devices & services**. If Home Assistant asks for a restart first, a repair under **Settings > System > Repairs** says so and can restart Home Assistant for you.
6. **After updating** the integration later, restart Home Assistant to apply the update (the Marketplace shows a repair as a reminder).

**Already using HACS?** Nothing to do. Home Assistant migrates HACS into the Marketplace on the first start after updating to 2026.11. Installed integrations, custom repositories and update entities carry over, and the HACS integration is removed. The separate HACS installer no longer works on 2026.11 and newer.

**Beta (pre-release) versions:** the Marketplace only offers stable releases by default. To try a pre-release: open **Settings > Devices & services > Marketplace**, open the entry for this repository, enable the **Pre-release** entity (it is disabled by default), and turn it on. Then update from the Marketplace as usual. You can also pick a specific version with the three-dots menu and **Install another version**, but don't use that to roll back; restore a backup instead.

### HACS Installation (Home Assistant before 2026.11)

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

To try a beta, enable "Show beta versions" in the HACS settings for this repository.

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

Starting with v0.5.0, this integration supports Gen 2 devices (WiFi + Bluetooth models with device names starting with `WD_V5_`, `WD_E5_`, `WD_V6_`, `WD_E6_`, or `WD_E7_`, such as PWD30EPOW/PWD50EPOW/PWD50EPOHW). These devices use a different BLE protocol than the Gen 1 Bluetooth-only models. The protocol header `$yw@` corresponds to the "yw" identifier used in the official [Power Watchdog WiFi](https://play.google.com/store/apps/details?id=com.yw.watchdog) app.

**Gen 2 (V2) Status:**
- Voltage, Current, Power readings - Working
- Energy (kWh) - Working
- Real-time push updates (v0.6.0) - Working
- Error codes - Working (v0.7.0)
- Frequency - Working (v0.7.0)
- Line 2 (50A dual-phase) - Working
- Neutral Detection, Power Factor - Working (v0.10.0). Gen 1 power factor sensors added in v0.12.0
- Device commands — relay, backlight, energy reset, error delete, clock sync - Working (v0.8.0)
- Output Voltage, Temperature, Boost Mode (booster models V8/V9/E8/E9 only) - **Untested**
- Neutral Detection Control switch - Working, reflects real device state (v0.10.0)
- Relay Status / Power Relay on/off indicator - Working on 30A (single-line) devices; experimental on 50A (dual-line) devices, where a commanded open was confirmed on a WD_E7 and WD_E5 (see [issue #17](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues/17) and [issue #26](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues/26))

> **Help wanted: Relay status on 50A (dual-line) devices (experimental).** Captures from a WD_E7 and a WD_E5 show bit `0x10` of byte 42 is set while the relay is open after a commanded open, and the integration now uses it. We still don't know whether it also covers an open you did not command (an over-current trip, or the power-up startup delay), or the behavior on other 50A models. If you have a **50A Gen 2 device** (dual-line, e.g. WD_E5/WD_E6/WD_V6/WD_E7), please post debug-log samples to **[issue #26](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues/26)**. See [Capturing Relay State Data (50A devices)](#capturing-relay-state-data-50a-devices) below for exact steps.

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

### Capturing Relay State Data (50A Devices)

If you have a 50A (dual-line) Gen 2 device, here's how to help confirm the experimental relay-status bit, especially for opens you did **not** command (a trip, or the power-up delay):

1. Enable debug logging (see above) and restart Home Assistant.
2. With the relay **closed** (power flowing normally), wait a few seconds, then open **Settings → System → Logs** (or your log file) and copy **5-10 consecutive lines** containing `V2: Complete packet` or `V2: Extended fields` for your device.
3. Open the relay using the **Power Relay** switch in Home Assistant. **Note whether the relay audibly or visibly clicked/opened** — this confirms whether the command itself reached the device, which hasn't been verified on 50A devices.
4. Wait 5-10 seconds — the status byte can lag a second or two on 30A devices, so give it time — then copy another **5-10 consecutive lines** of the same log entries.
5. Post both sets of log lines (labeled "relay closed" and "relay open"), whether the relay physically responded in step 3, and your exact device model (e.g. WD_E5, WD_E6, WD_V6, WD_E7), as a comment on **[a new issue](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues/new)**.
6. Close the relay again afterward via the switch to restore normal operation.

Debug logs include your device's raw BLE packet bytes but no personal information.

## Requirements

- Home Assistant 2024.11.0 or newer
- Bluetooth adapter/proxy in range of your Hughes Power Watchdog
- Hughes Power Watchdog with Bluetooth (Gen 1 or Gen 2)

## Troubleshooting

### Device Not Found
- Ensure no other devices are connected to your Hughes Power Watchdog (it only supports one connection at a time)
- Make sure Bluetooth is enabled on your Home Assistant host
- Verify your Hughes device is powered on and within Bluetooth range
- Try using the Hughes mobile app to confirm the device is functioning

### Entity Names Look Different After Updating to Home Assistant 2026.11
Home Assistant 2026.11 changed how dashboards label entities: a card, badge or row without a custom name now shows the device name followed by the entity name (for example "Power Watchdog Voltage Line 1") instead of just the entity's friendly name. Entity IDs, automations and scripts are not affected. This is a Home Assistant display change, not something the integration does; set a name on the card row if you prefer the old look. See the [2026.11 release notes](https://www.home-assistant.io/blog/2026/11/04/release-202611/).

### Connection Issues
- Disconnect any mobile apps connected to the Hughes device
- Toggle the Monitoring Switch off and on
- Restart the integration

## Development

Unit tests live in `tests/` and run with `pytest`. Using [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.13 .venv
uv pip install --prerelease=allow --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```

The `Tests` GitHub Action runs the same suite on pushes and pull requests to `main` and `development`.

## Credits

Based on the original ESPHome implementation by:
- [spbrogan](https://github.com/spbrogan)
- [makifoxgirl](https://github.com/makifoxgirl)
- [tango2590](https://github.com/tango2590/Hughes-Power-Watchdog)
- SergeantBort

V1/V2 protocol documentation reverse-engineered from the Android app source by:
- [gearhead765](https://github.com/gearhead765)
- [bmcgair](https://github.com/bmcgair) — Gen 1 (V1) command wire strings and acknowledgments (see [docs/protocol.md](docs/protocol.md))

Additional protocol details cross-referenced against the independent [TechBlueprints/dbus-power-watchdog](https://github.com/TechBlueprints/dbus-power-watchdog) Venus OS D-Bus service, which clarified the booster-model gating for V2 output voltage, temperature, and boost mode. See [docs/protocol.md](docs/protocol.md) for details.

### Contributors
- [IAmTheMitchell](https://github.com/IAmTheMitchell) — Gen 2 WD_E5 device support, V2 50A Line 2 sensor fix, protocol documentation for dual-block packet format
- [gearhead765](https://github.com/gearhead765) — Error Log feature and testing (v0.9.0)
- [bmcgair](https://github.com/bmcgair) — Gen 1 (V1) command wire format reverse-engineered from the official app, the Restart After Trip button (v0.11.0), and the project's first automated tests
- [brianfinley](https://github.com/brianfinley) — WD_V7 (PWD30EPOHW) device support and hardware testing (v0.10.2)
- [snoack](https://github.com/snoack) — Resubscribe after dropped BLE connections, remembering dual-line (50A) devices to fix missing Line 2 sensors, and fixing energy total drops (v0.10.3), per-line energy sensors (v0.11.0), and the 50A relay-state capture (#17)

## License

MIT License

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/john-k-mcdowell/My-Hughes-Power-Watchdog/issues).
