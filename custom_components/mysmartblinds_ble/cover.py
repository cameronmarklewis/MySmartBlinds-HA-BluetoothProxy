from __future__ import annotations

import logging

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import MySmartBlindsApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    api: MySmartBlindsApi = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MySmartBlindsCover(entry, api)])


class MySmartBlindsCover(RestoreEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, entry: ConfigEntry, api: MySmartBlindsApi) -> None:
        self._entry = entry
        self._api = api
        self._attr_unique_id = entry.unique_id or entry.data["address"]
        self._attr_translation_key = "blind"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": entry.data.get(CONF_NAME, api.device_name),
            "manufacturer": "MySmartBlinds",
            "model": "BLE Blind Motor",
            "connections": {("bluetooth", api.address)},
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if last_state := await self.async_get_last_state():
            try:
                last = int(last_state.attributes.get("current_position", 50))
            except (TypeError, ValueError):
                last = 50
            self._api.state.native_position = self._api.ha_to_native(last)
            self._api.state.available = True

    @property
    def available(self) -> bool:
        return self._api.state.available

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        return {
            "bluetooth_address": self._api.address,
            "native_position": self._api.state.native_position,
            "last_error": self._api.state.last_error,
        }

    @property
    def current_cover_position(self) -> int | None:
        return self._api.native_to_ha(self._api.state.native_position)

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        return None if pos is None else pos == 0

    async def _run_command(self, coro) -> None:
        try:
            await coro
            self._api.state.available = True
            self._api.state.last_error = None
        except Exception as err:
            self._api.state.available = False
            self._api.state.last_error = str(err)
            _LOGGER.warning("MySmartBlinds command failed for %s: %s", self._api.address, err)
            raise
        finally:
            self.async_write_ha_state()

    async def async_open_cover(self, **kwargs) -> None:
        await self._run_command(self._api.async_open())

    async def async_close_cover(self, **kwargs) -> None:
        await self._run_command(self._api.async_close())

    async def async_stop_cover(self, **kwargs) -> None:
        await self._run_command(self._api.async_stop())

    async def async_set_cover_position(self, **kwargs) -> None:
        await self._run_command(self._api.async_set_position(kwargs[ATTR_POSITION]))
