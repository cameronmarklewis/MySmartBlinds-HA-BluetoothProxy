from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_CLOSE_DIRECTION,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_WRITE_RETRIES,
    DISCOVER_KEY_MAX,
    HANDLE_KEY,
    HANDLE_SET,
    UUID_KEY,
    UUID_SET,
    KNOWN_LOCAL_NAMES,
    MAX_NATIVE_POSITION,
    MID_NATIVE_POSITION,
    MIN_NATIVE_POSITION,
)

_LOGGER = logging.getLogger(__name__)


class MySmartBlindsError(Exception):
    """Base integration error."""


class MySmartBlindsConnectionError(MySmartBlindsError):
    """Connection error."""


class MySmartBlindsCharacteristicError(MySmartBlindsError):
    """Characteristic lookup error."""


class MySmartBlindsValidationError(MySmartBlindsError):
    """Configuration or input validation error."""


@dataclass(slots=True)
class BlindState:
    native_position: int = MID_NATIVE_POSITION
    battery_level: int | None = None
    available: bool = False
    last_error: str | None = None


@dataclass(slots=True)
class DiscoveredBlind:
    address: str
    name: str | None
    rssi: int | None


class MySmartBlindsApi:
    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        key_hex: str,
        close_direction: str = DEFAULT_CLOSE_DIRECTION,
        connection_timeout: float = DEFAULT_CONNECTION_TIMEOUT,
        write_retries: int = DEFAULT_WRITE_RETRIES,
    ) -> None:
        self.hass = hass
        self.address = normalize_address(address)
        self.key = normalize_key(key_hex)
        self.close_direction = close_direction
        self.connection_timeout = max(5.0, float(connection_timeout))
        self.write_retries = max(1, int(write_retries))
        self.state = BlindState()
        self._lock = asyncio.Lock()

    @property
    def device_name(self) -> str:
        return f"MySmartBlinds {self.address[-5:].replace(':', '')}"

    async def async_shutdown(self) -> None:
        return None

    def native_to_ha(self, native_position: int) -> int:
        native_position = max(MIN_NATIVE_POSITION, min(MAX_NATIVE_POSITION, native_position))
        if self.close_direction == "up":
            return max(0, min(100, 100 - native_position))
        if native_position >= MID_NATIVE_POSITION:
            return max(0, 100 - (native_position - MID_NATIVE_POSITION))
        return native_position

    def ha_to_native(self, ha_position: int) -> int:
        ha_position = max(0, min(100, ha_position))
        if self.close_direction == "up":
            return 100 - ha_position
        return 200 - ha_position


    def is_device_present(self) -> bool:
        return (
            bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            is not None
        )

    async def async_refresh_availability(self) -> None:
        self.state.available = self.is_device_present()
        if self.state.available:
            self.state.last_error = None

    async def async_ping(self) -> None:
        async with self._lock:
            await _validate_connectivity(
                self.hass,
                self.address,
                self.connection_timeout,
                self.write_retries,
            )
            self.state.available = True
            self.state.last_error = None

    async def async_set_position(self, ha_position: int) -> None:
        native_position = self.ha_to_native(ha_position)
        await self.async_set_native_position(native_position)

    async def async_set_native_position(self, native_position: int) -> None:
        native_position = max(MIN_NATIVE_POSITION, min(MAX_NATIVE_POSITION, native_position))
        async with self._lock:
            await _write_position(
                self.hass,
                self.address,
                self.key,
                native_position,
                timeout=self.connection_timeout,
                max_attempts=self.write_retries,
            )
            self.state.native_position = native_position
            self.state.available = True
            self.state.last_error = None

    async def async_open(self) -> None:
        await self.async_set_position(100)

    async def async_close(self) -> None:
        await self.async_set_position(0)

    async def async_stop(self) -> None:
        await self.async_set_native_position(self.state.native_position)


def normalize_key(key_hex: str) -> bytes:
    raw = (key_hex or "").strip().replace(" ", "")
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) % 2 != 0 or not raw:
        raise MySmartBlindsValidationError("Key must be valid hex and contain whole bytes")
    try:
        return bytes.fromhex(raw)
    except ValueError as err:
        raise MySmartBlindsValidationError("Key must be valid hex") from err


def normalize_address(address: str) -> str:
    raw = (address or "").strip().upper()
    parts = raw.split(":")
    if len(parts) != 6 or any(len(p) != 2 for p in parts):
        raise MySmartBlindsValidationError("Bluetooth address must be in AA:BB:CC:DD:EE:FF format")
    return raw


async def discover_devices(hass: HomeAssistant) -> list[DiscoveredBlind]:
    candidates: dict[str, DiscoveredBlind] = {}
    for svc in bluetooth.async_discovered_service_info(hass, connectable=True):
        name = getattr(svc, "name", None) or getattr(svc, "local_name", None)
        manufacturer_data = getattr(svc, "manufacturer_data", None) or {}
        service_uuids = {u.lower() for u in (getattr(svc, "service_uuids", None) or [])}
        looks_like_blind = (
            (name in KNOWN_LOCAL_NAMES)
            or any("1409" in uuid or "140b" in uuid for uuid in service_uuids)
            or bool(manufacturer_data)
        )
        if not looks_like_blind:
            continue
        address = normalize_address(svc.address)
        current = candidates.get(address)
        if current is None or (svc.rssi is not None and (current.rssi is None or svc.rssi > current.rssi)):
            candidates[address] = DiscoveredBlind(address=address, name=name, rssi=svc.rssi)
    return sorted(candidates.values(), key=lambda item: (item.name or "", item.address))


async def discover_key(
    hass: HomeAssistant,
    address: str,
    attempts: int = 256,
    *,
    timeout: float = DEFAULT_CONNECTION_TIMEOUT,
    max_attempts: int = 2,
    native_position: int = MAX_NATIVE_POSITION,
) -> str | None:
    address = normalize_address(address)
    attempts = max(1, min(attempts, DISCOVER_KEY_MAX + 1))
    for guess in range(attempts):
        try:
            await _write_position(
                hass,
                address,
                bytes([guess]),
                native_position,
                timeout=timeout,
                max_attempts=max_attempts,
            )
            return f"{guess:02x}"
        except MySmartBlindsError:
            continue
    return None


async def _validate_connectivity(
    hass: HomeAssistant,
    address: str,
    timeout: float,
    max_attempts: int,
) -> None:
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise MySmartBlindsConnectionError(
            f"Bluetooth device {address} is not currently available to Home Assistant"
        )

    client: BleakClient | None = None
    try:
        client = await establish_connection(
            BleakClient,
            ble_device,
            address,
            max_attempts=max_attempts,
            timeout=timeout,
        )
        _resolve_write_target(client, HANDLE_KEY, UUID_KEY)
        _resolve_write_target(client, HANDLE_SET, UUID_SET)
    except Exception as err:
        raise MySmartBlindsConnectionError(str(err)) from err
    finally:
        if client and client.is_connected:
            await client.disconnect()


async def _write_position(
    hass: HomeAssistant,
    address: str,
    key: bytes,
    native_position: int,
    *,
    timeout: float,
    max_attempts: int,
) -> None:
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise MySmartBlindsConnectionError(
            f"Bluetooth device {address} is not currently available to Home Assistant"
        )

    client: BleakClient | None = None
    try:
        client = await establish_connection(
            BleakClient,
            ble_device,
            address,
            max_attempts=max_attempts,
            timeout=timeout,
        )
        key_char = _resolve_write_target(client, HANDLE_KEY, UUID_KEY)
        set_char = _resolve_write_target(client, HANDLE_SET, UUID_SET)
        _LOGGER.debug("Writing key and target position to %s via BLE", address)
        await client.write_gatt_char(key_char, key, response=True)
        await client.write_gatt_char(set_char, bytes([native_position]), response=True)
    except Exception as err:
        raise MySmartBlindsConnectionError(str(err)) from err
    finally:
        if client and client.is_connected:
            await client.disconnect()


def _resolve_write_target(
    client: BleakClient, handle: int, uuid: str
) -> BleakGATTCharacteristic | str:
    services = getattr(client, "services", None)
    if services is not None:
        try:
            for service in services:
                for char in service.characteristics:
                    if getattr(char, "handle", None) == handle:
                        return char
        except Exception:
            pass

        try:
            characteristic = services.get_characteristic(uuid)
            if characteristic is not None:
                return characteristic
        except Exception:
            pass

    return uuid
