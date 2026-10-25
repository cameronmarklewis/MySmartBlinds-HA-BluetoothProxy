# MySmartBlinds BLE for Home Assistant

Local Bluetooth control for legacy MySmartBlinds tilt motors using Home Assistant’s
Bluetooth adapter or an active ESPHome Bluetooth proxy. Once configured, commands
stay local: a MySmartBlinds account, bridge and internet connection are not needed
for day-to-day control.

This is an unofficial community integration, independent of MySmartBlinds,
Tilt and SmarterHome. It is intended for legacy tilt motors advertising as
`SmartBlind` or `SmartBlind_DFU`, not Tilt roller shades or other Bluetooth blinds.

## Requirements

- Home Assistant with Bluetooth support and an adapter or active ESPHome Bluetooth proxy within range.
- The motor’s Bluetooth address and pairing key, or locally cached credentials from an existing installation.
- Home Assistant 2026.3 or newer to display the bundled integration icon.

Existing configured blinds keep their credentials and continue operating locally.
Keep a private backup of your Home Assistant configuration and the app’s exported
backup; pairing keys are needed if you reinstall or move to another controller.

## Installation

### HACS

1. Add `https://github.com/cameronmarklewis/MySmartBlinds-HA-BluetoothProxy` as a custom repository of type **Integration**.
2. Download **MySmartBlinds BLE**.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → MySmartBlinds BLE**.

### Manual installation

Copy `custom_components/mysmartblinds_ble` from the latest release into your
Home Assistant `config/custom_components/` directory, then restart Home Assistant.

## Setup

1. Enter the blind’s Bluetooth address and choose a name.
2. Adjust the close direction if needed; the other settings can usually stay at their defaults.
3. Choose **Enter key manually** and enter the motor’s pairing key as hexadecimal bytes.
4. Test opening and closing while you can see the blind, then adjust its close direction if necessary.

Previously saved credentials may be reused automatically when the address matches.
Some older exports represent Bluetooth addresses in reverse byte order; use the
address advertised by the motor in Home Assistant.

The MySmartBlinds app has moved to offline operation and supports backup export/import.
The legacy cloud-login option remains in this release for compatibility, but it
is not required for local control and may no longer work. The legacy automatic
key-discovery option cannot reliably establish whether a guessed key is correct;
use a known pairing key instead. Native app JSON upload support is in development
and is not included in 0.3.2.

## Controls and limitations

The integration exposes Open, Close, Stop and a position slider.

- **Position is optimistic.** Home Assistant displays the requested position, not a measurement from the motor. A successful Bluetooth write does not prove physical movement.
- **Stop is approximate.** It resends the last requested position; immediate stopping during travel is not verified.
- Firmware variants can expose different GATT handles. This integration identifies writable command endpoints by UUID and rejects missing or ambiguous endpoints rather than guessing.
- Setup may succeed with an incorrect pairing key because Bluetooth transport success alone does not verify authentication.
- A motor may allow only one active Bluetooth connection. Close the phone app when troubleshooting Home Assistant control.
- Bluetooth proxy range and active connection capacity can limit reliability.
- Battery reporting, calibration and on-motor schedule management are not implemented.

## Troubleshooting

Check that the Bluetooth adapter or proxy is online, active connections are enabled,
and the motor is in range. Confirm the Bluetooth address, pairing key and battery
condition. Integration diagnostics include the resolved GATT handles and discovered
characteristics without exposing the configured pairing key.

The `last_error` attribute retains command errors until a successful command or
connectivity check. Seeing an advertisement alone does not clear it.

Use **MySmartBlinds BLE: Ping blind** to check that Home Assistant can connect and
find the required endpoints. Ping does not authenticate, move the motor or verify
the pairing key. **Scan devices** lists nearby candidate motors.

When reporting an issue, include Home Assistant and integration versions, the motor
model/firmware if known, proxy type and a description of the observed behaviour.
Do not post app backups, pairing keys or account credentials.

## Updates

Published GitHub releases appear as updates in HACS after its repository metadata
refresh. To check sooner, open this repository in HACS and select **⋮ → Update
information**. Installing an integration update requires a Home Assistant restart.
Update detection and automatic installation are separate settings.

## Development

Run the isolated Bluetooth regression suite without a Home Assistant installation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_mysmartblinds_ble.py
```

Tests use synthetic credentials and cover firmware/proxy handle differences,
endpoint validation, command ordering, disconnect handling and error retention.
The command path has also been checked on a legacy tilt motor with physical
movement confirmed in both directions; other hardware/firmware combinations may differ.

## Branding

The original MySmartBlinds icon is bundled in the integration’s `brand/` directory
and served locally by Home Assistant 2026.3 or newer. MySmartBlinds branding belongs
to its respective owner and does not imply endorsement of this integration.
