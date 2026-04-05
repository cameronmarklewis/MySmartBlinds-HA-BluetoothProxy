from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .api import MySmartBlindsApi
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    api: MySmartBlindsApi = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "data": {
            "address": entry.data.get("address"),
            "close_direction": entry.data.get("close_direction"),
            "connection_timeout": entry.data.get("connection_timeout"),
            "write_retries": entry.data.get("write_retries"),
            "key_length": len(api.key),
        },
        "options": dict(entry.options),
        "runtime": {
            "address": api.address,
            "available": api.state.available,
            "native_position": api.state.native_position,
            "last_error": api.state.last_error,
            "resolved_key_handle": api.state.resolved_key_handle,
            "resolved_set_handle": api.state.resolved_set_handle,
            "gatt_snapshot": api.state.gatt_snapshot,
        },
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict:
    return await async_get_config_entry_diagnostics(hass, entry)
