from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient
from bleak.exc import BleakCharacteristicNotFoundError
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
    resolved_key_handle: int | None = None
    resolved_set_handle: int | None = None
    gatt_snapshot: list[str] | None = None


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
        self._preferred_key_handle = HANDLE_KEY
        self._preferred_set_handle = HANDLE_SET
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
                self,
            )
            self.state.available = True
            self.state.last_error = None

    async def async_set_position(self, ha_position: int) -> None:
        native_position = self.ha_to_native(ha_position)
        await self.async_set_native_position(native_position)

    async def async_set_native_position(self, native_position: int) -> None:
        native_position = max(MIN_NATIVE_POSITION, min(MAX_NATIVE_POSITION, native_position))
        async with self._lock:
            key_handle, set_handle = await _write_position(
                self.hass,
                self.address,
                self.key,
                native_position,
                timeout=self.connection_timeout,
                max_attempts=self.write_retries,
                api=self,
            )
            self._preferred_key_handle = key_handle
            self._preferred_set_handle = set_handle
            self.state.resolved_key_handle = key_handle
            self.state.resolved_set_handle = set_handle
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
    api: MySmartBlindsApi | None = None,
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
        await _async_resolve_backend_characteristic(
            client, (api._preferred_key_handle if api else HANDLE_KEY), UUID_KEY, "key", api
        )
        await _async_resolve_backend_characteristic(
            client, (api._preferred_set_handle if api else HANDLE_SET), UUID_SET, "set", api
        )
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
    api: MySmartBlindsApi | None = None,
) -> tuple[int, int]:
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
        preferred_key = api._preferred_key_handle if api else HANDLE_KEY
        preferred_set = api._preferred_set_handle if api else HANDLE_SET
        key_char = await _async_resolve_backend_characteristic(client, preferred_key, UUID_KEY, "key", api)
        set_char = await _async_resolve_backend_characteristic(client, preferred_set, UUID_SET, "set", api)
        _LOGGER.debug("Writing key and target position to %s via BLE using key handle %s and set handle %s", address, getattr(key_char, "handle", preferred_key), getattr(set_char, "handle", preferred_set))
        await _async_write_char(client, key_char, getattr(key_char, "handle", preferred_key), UUID_KEY, key)
        await _async_write_char(client, set_char, getattr(set_char, "handle", preferred_set), UUID_SET, bytes([native_position]))
        return getattr(key_char, "handle", preferred_key), getattr(set_char, "handle", preferred_set)
    except Exception as err:
        raise MySmartBlindsConnectionError(str(err)) from err
    finally:
        if client and client.is_connected:
            await client.disconnect()


async def _async_write_char(
    client: BleakClient,
    resolved_target,
    handle: int,
    uuid: str,
    data: bytes,
) -> None:
    try:
        await client.write_gatt_char(resolved_target, data, response=True)
        return
    except BleakCharacteristicNotFoundError:
        _LOGGER.debug(
            "Characteristic lookup failed for handle 0x%04x / %s via wrapper, retrying without response",
            handle,
            uuid,
        )
    except Exception as err:
        message = str(err).lower()
        if "error=133" in message or "unlikely error" in message:
            _LOGGER.debug(
                "Write-with-response failed for handle 0x%04x / %s, retrying without response: %s",
                handle,
                uuid,
                err,
            )
        else:
            raise

    await client.write_gatt_char(resolved_target, data, response=False)


async def _async_resolve_backend_characteristic(
    client: BleakClient,
    handle: int,
    uuid: str,
    purpose: str,
    api: MySmartBlindsApi | None = None,
):
    backend = getattr(client, "_backend", None)
    discovered: list[tuple[int | None, str, list[str]]] = []

    services_sources = []

    wrapper_services = getattr(client, "services", None)
    if wrapper_services is not None:
        services_sources.append(wrapper_services)

    if backend is not None:
        backend_get_services = getattr(backend, "get_services", None)
        if callable(backend_get_services):
            try:
                await backend_get_services()
            except Exception as err:
                _LOGGER.debug("Backend service refresh failed for %s handle 0x%04x / %s: %s", purpose, handle, uuid, err)
        for source_name in ("services", "_services"):
            svc = getattr(backend, source_name, None)
            if svc is not None:
                services_sources.append(svc)

    # exact handle / uuid first
    for services in services_sources:
        try:
            for service in services:
                for char in service.characteristics:
                    ch_handle = getattr(char, "handle", None)
                    ch_uuid = str(getattr(char, "uuid", "")).lower()
                    props = list(getattr(char, "properties", []) or [])
                    discovered.append((ch_handle, ch_uuid, props))
                    if ch_handle == handle:
                        _store_gatt_snapshot(api, discovered)
                        return char
        except Exception:
            pass
        try:
            characteristic = services.get_characteristic(uuid)
            if characteristic is not None:
                _store_gatt_snapshot(api, discovered)
                return characteristic
        except Exception:
            pass

    # heuristic fallback: nearest writable characteristic near expected handle
    writable_candidates = []
    for ch_handle, ch_uuid, props in discovered:
        if ch_handle is None:
            continue
        p = {str(x).lower() for x in props}
        if "write" in p or "write-without-response" in p:
            writable_candidates.append((abs(ch_handle - handle), ch_handle, ch_uuid, props))

    if writable_candidates:
        writable_candidates.sort(key=lambda x: (x[0], x[1]))
        nearest_distance, nearest_handle, nearest_uuid, nearest_props = writable_candidates[0]
        # only trust nearby handles
        if nearest_distance <= 6:
            _LOGGER.warning(
                "MySmartBlinds %s characteristic 0x%04x / %s not found exactly. Using nearby writable handle 0x%04x (%s) with props %s",
                purpose,
                handle,
                uuid,
                nearest_handle,
                nearest_uuid,
                nearest_props,
            )
            for services in services_sources:
                try:
                    for service in services:
                        for char in service.characteristics:
                            if getattr(char, "handle", None) == nearest_handle:
                                _store_gatt_snapshot(api, discovered)
                                return char
                except Exception:
                    pass

    _store_gatt_snapshot(api, discovered)
    raise MySmartBlindsCharacteristicError(
        f"Could not resolve characteristic handle 0x{handle:04x} / {uuid} from backend services"
    )


def _store_gatt_snapshot(api: MySmartBlindsApi | None, discovered: list[tuple[int | None, str, list[str]]]) -> None:
    if api is None:
        return
    api.state.gatt_snapshot = [
        f"{handle}:{uuid}:{','.join(props)}" for handle, uuid, props in discovered
    ]


def _resolve_write_target(
    client: BleakClient, handle: int, uuid: str
):
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
    return handle
