from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.const import CONF_NAME

from .api import MySmartBlindsApi, MySmartBlindsValidationError, discover_devices, normalize_address, normalize_key
from .const import (
    CONF_ADDRESS,
    CONF_CLOSE_DIRECTION,
    CONF_CONNECTION_TIMEOUT,
    CONF_KEY,
    CONF_WRITE_RETRIES,
    DEFAULT_CLOSE_DIRECTION,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_WRITE_RETRIES,
    DOMAIN,
    KNOWN_LOCAL_NAMES,
)

CLOSE_DIRECTION_OPTIONS = ["down", "up"]


class MySmartBlindsBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                address = normalize_address(user_input[CONF_ADDRESS])
                normalize_key(user_input[CONF_KEY])
            except MySmartBlindsValidationError:
                errors["base"] = "invalid_input"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                title = user_input.get(CONF_NAME) or f"MySmartBlinds {address[-5:]}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_NAME: user_input.get(CONF_NAME) or "MySmartBlinds",
                        CONF_ADDRESS: address,
                        CONF_KEY: user_input[CONF_KEY].lower().replace(" ", ""),
                        CONF_CLOSE_DIRECTION: user_input[CONF_CLOSE_DIRECTION],
                        CONF_CONNECTION_TIMEOUT: user_input[CONF_CONNECTION_TIMEOUT],
                        CONF_WRITE_RETRIES: user_input[CONF_WRITE_RETRIES],
                    },
                )

        discovered = await discover_devices(self.hass)
        suggestions = [item.address for item in discovered]
        default_address = self.context.get("default_address") or (suggestions[0] if suggestions else "")

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_ADDRESS, default=default_address): str,
                vol.Required(CONF_KEY): str,
                vol.Optional(CONF_CLOSE_DIRECTION, default=DEFAULT_CLOSE_DIRECTION): vol.In(
                    CLOSE_DIRECTION_OPTIONS
                ),
                vol.Optional(
                    CONF_CONNECTION_TIMEOUT, default=DEFAULT_CONNECTION_TIMEOUT
                ): vol.All(vol.Coerce(float), vol.Range(min=5, max=60)),
                vol.Optional(
                    CONF_WRITE_RETRIES, default=DEFAULT_WRITE_RETRIES
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "discovered": ", ".join(suggestions[:5]) or "none currently visible"
            },
        )

    async def async_step_bluetooth(self, discovery_info):
        if discovery_info.name and discovery_info.name not in KNOWN_LOCAL_NAMES:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        self.context["default_address"] = discovery_info.address
        return await self.async_step_user()

    @staticmethod
    def async_get_options_flow(config_entry):
        return MySmartBlindsBleOptionsFlow(config_entry)


class MySmartBlindsBleOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CLOSE_DIRECTION,
                    default=self.config_entry.options.get(
                        CONF_CLOSE_DIRECTION,
                        self.config_entry.data.get(CONF_CLOSE_DIRECTION, DEFAULT_CLOSE_DIRECTION),
                    ),
                ): vol.In(CLOSE_DIRECTION_OPTIONS),
                vol.Optional(
                    CONF_CONNECTION_TIMEOUT,
                    default=self.config_entry.options.get(
                        CONF_CONNECTION_TIMEOUT,
                        self.config_entry.data.get(
                            CONF_CONNECTION_TIMEOUT, DEFAULT_CONNECTION_TIMEOUT
                        ),
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=5, max=60)),
                vol.Optional(
                    CONF_WRITE_RETRIES,
                    default=self.config_entry.options.get(
                        CONF_WRITE_RETRIES,
                        self.config_entry.data.get(CONF_WRITE_RETRIES, DEFAULT_WRITE_RETRIES),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
