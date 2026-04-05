from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import MySmartBlindsApi, discover_devices, discover_key
from .const import (
    ATTR_ATTEMPTS,
    ATTR_DEVICES,
    ATTR_DISCOVERED_KEY,
    ATTR_LAST_ERROR,
    ATTR_NAME,
    ATTR_RSSI,
    CONF_ADDRESS,
    DEFAULT_CLOSE_DIRECTION,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_WRITE_RETRIES,
    DOMAIN,
    PLATFORMS,
    SERVICE_DISCOVER_KEY,
    SERVICE_PING,
    SERVICE_SCAN_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_DISCOVER_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(ATTR_ATTEMPTS, default=256): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=256)
        ),
    }
)

SERVICE_PING_SCHEMA = vol.Schema({vol.Required(CONF_ADDRESS): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    async def _handle_discover_key(call: ServiceCall) -> None:
        address = call.data[CONF_ADDRESS]
        attempts = call.data[ATTR_ATTEMPTS]
        found = await discover_key(hass, address, attempts)
        hass.states.async_set(
            f"{DOMAIN}.keyscan_{address.lower().replace(':', '_')}",
            "found" if found is not None else "not_found",
            {
                CONF_ADDRESS: address,
                ATTR_ATTEMPTS: attempts,
                ATTR_DISCOVERED_KEY: found,
            },
        )

    async def _handle_scan_devices(call: ServiceCall) -> None:
        devices = await discover_devices(hass)
        hass.states.async_set(
            f"{DOMAIN}.discovery",
            "ready",
            {
                ATTR_DEVICES: [
                    {
                        CONF_ADDRESS: item.address,
                        ATTR_NAME: item.name,
                        ATTR_RSSI: item.rssi,
                    }
                    for item in devices
                ]
            },
        )

    async def _handle_ping(call: ServiceCall) -> None:
        address = call.data[CONF_ADDRESS].upper()
        api = next(
            (candidate for candidate in hass.data[DOMAIN].values() if candidate.address == address),
            None,
        )
        if api is None:
            raise HomeAssistantError(f"No configured blind found for {address}")
        try:
            await api.async_ping()
            hass.states.async_set(
                f"{DOMAIN}.ping_{address.lower().replace(':', '_')}",
                "ok",
                {CONF_ADDRESS: address},
            )
        except Exception as err:
            hass.states.async_set(
                f"{DOMAIN}.ping_{address.lower().replace(':', '_')}",
                "error",
                {CONF_ADDRESS: address, ATTR_LAST_ERROR: str(err)},
            )
            raise

    hass.services.async_register(
        DOMAIN,
        SERVICE_DISCOVER_KEY,
        _handle_discover_key,
        schema=SERVICE_DISCOVER_KEY_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_SCAN_DEVICES, _handle_scan_devices)
    hass.services.async_register(
        DOMAIN,
        SERVICE_PING,
        _handle_ping,
        schema=SERVICE_PING_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = MySmartBlindsApi(
        hass=hass,
        address=entry.data[CONF_ADDRESS],
        key_hex=entry.data["key"],
        close_direction=entry.options.get(
            "close_direction", entry.data.get("close_direction", DEFAULT_CLOSE_DIRECTION)
        ),
        connection_timeout=entry.options.get(
            "connection_timeout", entry.data.get("connection_timeout", DEFAULT_CONNECTION_TIMEOUT)
        ),
        write_retries=entry.options.get(
            "write_retries", entry.data.get("write_retries", DEFAULT_WRITE_RETRIES)
        ),
    )
    hass.data[DOMAIN][entry.entry_id] = api
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api: MySmartBlindsApi = hass.data[DOMAIN].pop(entry.entry_id)
        await api.async_shutdown()
    return unload_ok
