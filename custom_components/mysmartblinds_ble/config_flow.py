from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .api import MySmartBlindsValidationError, discover_devices, discover_key, normalize_address, normalize_key
from .cloud import CloudBlind, MySmartBlindsCloudError, async_fetch_cloud_blinds
from .const import (
    CONF_ADDRESS,
    CONF_CLOUD_BLIND,
    CONF_CLOSE_DIRECTION,
    CONF_CONNECTION_TIMEOUT,
    CONF_DISCOVERY_ATTEMPTS,
    CONF_KEY,
    CONF_KEY_SOURCE,
    CONF_PASSWORD,
    CONF_SETUP_METHOD,
    CONF_USERNAME,
    CONF_WRITE_RETRIES,
    DEFAULT_CLOSE_DIRECTION,
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_KEY_DISCOVERY_ATTEMPTS,
    DEFAULT_NAME,
    DEFAULT_WRITE_RETRIES,
    DOMAIN,
    KEY_SOURCE_AUTO,
    KEY_SOURCE_CLOUD,
    KEY_SOURCE_MANUAL,
    KNOWN_LOCAL_NAMES,
    OPTION_AUTO,
    OPTION_CLOUD,
    OPTION_MANUAL,
)

CLOSE_DIRECTION_OPTIONS = ["down", "up"]

class MySmartBlindsBleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 3

    def __init__(self) -> None:
        self._config: dict[str, object] = {}
        self._cloud_blinds: list[CloudBlind] = []
        self._autodiscovered_key: str | None = None
        self._auto_error: str | None = None
        self._cloud_error: str | None = None

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        discovered = await discover_devices(self.hass)
        suggestions = [item.address for item in discovered]
        default_address = self.context.get("default_address") or (suggestions[0] if suggestions else "")

        if user_input is not None:
            try:
                address = normalize_address(user_input[CONF_ADDRESS])
            except MySmartBlindsValidationError:
                errors["base"] = "invalid_address"
            else:
                self._config = {
                    CONF_NAME: user_input.get(CONF_NAME) or DEFAULT_NAME,
                    CONF_ADDRESS: address,
                    CONF_CLOSE_DIRECTION: user_input[CONF_CLOSE_DIRECTION],
                    CONF_CONNECTION_TIMEOUT: user_input[CONF_CONNECTION_TIMEOUT],
                    CONF_WRITE_RETRIES: user_input[CONF_WRITE_RETRIES],
                    CONF_DISCOVERY_ATTEMPTS: user_input[CONF_DISCOVERY_ATTEMPTS],
                }
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                return await self.async_step_setup_method()

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_ADDRESS, default=default_address): str,
                vol.Optional(CONF_CLOSE_DIRECTION, default=DEFAULT_CLOSE_DIRECTION): vol.In(
                    CLOSE_DIRECTION_OPTIONS
                ),
                vol.Optional(
                    CONF_CONNECTION_TIMEOUT, default=DEFAULT_CONNECTION_TIMEOUT
                ): vol.All(vol.Coerce(float), vol.Range(min=5, max=60)),
                vol.Optional(
                    CONF_WRITE_RETRIES, default=DEFAULT_WRITE_RETRIES
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                vol.Optional(
                    CONF_DISCOVERY_ATTEMPTS, default=DEFAULT_KEY_DISCOVERY_ATTEMPTS
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=256)),
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

    async def async_step_setup_method(self, user_input=None):
        return self.async_show_menu(
            step_id="setup_method",
            menu_options=["auto_discover", "cloud_login", "manual_key"],
            description_placeholders={"address": str(self._config.get(CONF_ADDRESS, ""))},
        )

    async def async_step_auto_discover(self, user_input=None):
        address = str(self._config[CONF_ADDRESS])
        attempts = int(self._config[CONF_DISCOVERY_ATTEMPTS])
        timeout = float(self._config[CONF_CONNECTION_TIMEOUT])
        retries = int(self._config[CONF_WRITE_RETRIES])

        found = await discover_key(
            self.hass,
            address,
            attempts,
            timeout=timeout,
            max_attempts=retries,
        )
        self._autodiscovered_key = found
        if found is not None:
            return self._create_entry(found, KEY_SOURCE_AUTO)

        self._auto_error = (
            f"No key found for {address} after trying {attempts} candidate values."
        )
        return await self.async_step_auto_failed()

    async def async_step_auto_failed(self, user_input=None):
        return self.async_show_menu(
            step_id="auto_failed",
            menu_options=["cloud_login", "manual_key"],
            description_placeholders={"error": self._auto_error or "Key discovery failed."},
        )

    async def async_step_cloud_login(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                blinds = await async_fetch_cloud_blinds(self.hass, username, password)
            except MySmartBlindsCloudError as err:
                self._cloud_error = str(err)
                errors["base"] = "cloud_login_failed"
            else:
                self._cloud_blinds = blinds
                self._config[CONF_USERNAME] = username
                self._config[CONF_PASSWORD] = password
                address = str(self._config[CONF_ADDRESS])
                match = next((blind for blind in blinds if blind.address == address), None)
                if match is not None:
                    return self._create_entry(match.key_hex, KEY_SOURCE_CLOUD)
                return await self.async_step_cloud_select()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="cloud_login",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "address": str(self._config.get(CONF_ADDRESS, "")),
                "error": self._cloud_error or "",
            },
        )

    async def async_step_cloud_select(self, user_input=None):
        if user_input is not None:
            selected = user_input[CONF_CLOUD_BLIND]
            blind = next(
                (item for item in self._cloud_blinds if item.encoded_mac == selected),
                None,
            )
            if blind is not None:
                self._config[CONF_ADDRESS] = blind.address
                await self.async_set_unique_id(blind.address)
                self._abort_if_unique_id_configured()
                return self._create_entry(blind.key_hex, KEY_SOURCE_CLOUD)

        options = {
            blind.encoded_mac: f"{blind.display_name} ({blind.address})"
            for blind in self._cloud_blinds
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_CLOUD_BLIND): vol.In(options),
            }
        )
        return self.async_show_form(
            step_id="cloud_select",
            data_schema=schema,
            description_placeholders={
                "address": str(self._config.get(CONF_ADDRESS, "")),
                "count": str(len(self._cloud_blinds)),
            },
        )

    async def async_step_manual_key(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalize_key(user_input[CONF_KEY])
            except MySmartBlindsValidationError:
                errors["base"] = "invalid_key"
            else:
                return self._create_entry(user_input[CONF_KEY], KEY_SOURCE_MANUAL)

        schema = vol.Schema(
            {
                vol.Required(CONF_KEY, default=self._autodiscovered_key or ""): str,
            }
        )
        return self.async_show_form(
            step_id="manual_key",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_bluetooth(self, discovery_info):
        if discovery_info.name and discovery_info.name not in KNOWN_LOCAL_NAMES:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        self.context["default_address"] = discovery_info.address
        return await self.async_step_user()

    def _create_entry(self, key_hex: str, key_source: str):
        title = str(self._config.get(CONF_NAME) or f"MySmartBlinds {str(self._config[CONF_ADDRESS])[-5:]}")
        return self.async_create_entry(
            title=title,
            data={
                CONF_NAME: self._config.get(CONF_NAME) or DEFAULT_NAME,
                CONF_ADDRESS: self._config[CONF_ADDRESS],
                CONF_KEY: key_hex.lower().replace(" ", ""),
                CONF_KEY_SOURCE: key_source,
                CONF_CLOSE_DIRECTION: self._config[CONF_CLOSE_DIRECTION],
                CONF_CONNECTION_TIMEOUT: self._config[CONF_CONNECTION_TIMEOUT],
                CONF_WRITE_RETRIES: self._config[CONF_WRITE_RETRIES],
            },
        )

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
