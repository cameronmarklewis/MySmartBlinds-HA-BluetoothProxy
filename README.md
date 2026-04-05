# MySmartBlinds BLE for Home Assistant

A Home Assistant custom integration for controlling MySmartBlinds motors directly over native Bluetooth, including ESPHome Bluetooth Proxy.

## What changed in v2

- Better input validation for MAC address and key format
- Configurable timeout and write retries in the UI
- Diagnostics support for Home Assistant
- Extra debug-friendly state attributes, including the last error seen
- `scan_devices` service to list likely nearby blind motors
- `ping` service to test a configured blind through the Home Assistant Bluetooth stack
- HACS-ready repo layout and metadata

## Known limitations

- This is based on the reverse-engineered BLE protocol and is still hardware-unverified.
- Position is optimistic. The BLE protocol used by public libraries does not provide reliable state readback.
- Key discovery is only designed for the common one-byte key pattern.
- Bluetooth proxies have limited active connection slots, so a busy ESP32 proxy can still be the bottleneck.

## Install

Copy `custom_components/mysmartblinds_ble` into your Home Assistant `config/custom_components/` folder and restart Home Assistant.

For HACS, place this repo on GitHub and add it as a custom repository of type **Integration**.

## Services

### discover_key

```yaml
service: mysmartblinds_ble.discover_key
data:
  address: AA:BB:CC:DD:EE:FF
  attempts: 256
```

### scan_devices

```yaml
service: mysmartblinds_ble.scan_devices
```

Results are published to `mysmartblinds_ble.discovery` with a `devices` attribute.

### ping

```yaml
service: mysmartblinds_ble.ping
data:
  address: AA:BB:CC:DD:EE:FF
```

## Notes for Bluetooth Proxy

Use an ESPHome Bluetooth Proxy with active connections enabled. If you have several active BLE devices, increase proxy capacity carefully.
