# MySmartBlinds BLE for Home Assistant

A Home Assistant custom integration for controlling MySmartBlinds motors directly over native Bluetooth, including ESPHome Bluetooth Proxy.

## Bluetooth command endpoint fix

Movement commands use UUID `00001403-1212-efde-1600-785feabcd123` after
writing the configured pairing key to `00001409-1212-efde-1600-785feabcd123`.
GATT handle numbers differ between firmware and Bluetooth proxy backends, so
endpoints are resolved by their writable UUID. Missing or ambiguous endpoints
raise an error instead of falling back to an unrelated writable handle.
Command errors remain visible until a successful command or connectivity check.

Validated on 25 October 2026 with a Kitchen MySmartBlinds motor: open and close
commands completed through Home Assistant Bluetooth, and physical movement in
both directions was confirmed. Other motors have not yet been physically tested.
Position remains optimistic; a successful BLE write does not prove movement.

Run the isolated regression suite with:

```sh
python3 tests/test_mysmartblinds_ble.py
```

## What changed in v3

- Setup dialog now supports three key paths: Bluetooth auto-discovery, MySmartBlinds cloud login, or manual key entry
- Cloud login uses the same Auth0 and GraphQL flow used by the Homebridge bridge plugin to fetch encoded blind data
- Cloud results are decoded into BLE MAC addresses and passkeys so you can keep using local Bluetooth control after setup
- Auto-discovery still works as the first local-only path for the common one-byte key pattern

## Known limitations

- This uses a reverse-engineered BLE protocol. Hardware validation currently covers one Kitchen tilt motor; other firmware variants may differ.
- Position is optimistic. The BLE protocol used by public libraries does not provide reliable state readback.
- Auto key discovery is only designed for the common one-byte key pattern.
- Bluetooth proxies have limited active connection slots, so a busy ESP32 proxy can still be the bottleneck.
- The cloud login path depends on an unofficial API used by community projects, so service-side changes may break it in future.

## Install

Copy `custom_components/mysmartblinds_ble` into your Home Assistant `config/custom_components/` folder and restart Home Assistant.

For HACS, place this repo on GitHub and add it as a custom repository of type **Integration**.

## Setup

1. Add the integration in Home Assistant.
2. Pick the blind address.
3. Choose one of:
   - **Auto discover key over Bluetooth**
   - **Sign in and fetch key from MySmartBlinds account**
   - **Enter key manually**
4. The resulting key is stored locally in the config entry and the cover continues to use local BLE control.

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


## Icon

This package includes the MySmartBlinds BLE icon as `icon.png` and `icon.webp`.
