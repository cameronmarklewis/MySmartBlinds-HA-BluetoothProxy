from __future__ import annotations

import base64
from dataclasses import dataclass

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    MYSMARTBLINDS_AUTH_REALM,
    MYSMARTBLINDS_AUTH_SCOPE,
    MYSMARTBLINDS_AUTH_URL,
    MYSMARTBLINDS_CLIENT_ID,
    MYSMARTBLINDS_GRAPHQL_URL,
    MYSMARTBLINDS_QUERY_GET_USER_INFO,
    MYSMARTBLINDS_USER_AGENT,
)


class MySmartBlindsCloudError(Exception):
    """Cloud API error."""


@dataclass(slots=True)
class CloudBlind:
    name: str
    room_name: str | None
    encoded_mac: str
    encoded_passkey: str
    address: str
    reversed_address: str
    key_hex: str

    @property
    def display_name(self) -> str:
        if self.room_name:
            return f"{self.room_name} {self.name}".strip()
        return self.name


async def async_fetch_cloud_blinds(
    hass: HomeAssistant,
    username: str,
    password: str,
) -> list[CloudBlind]:
    session = async_get_clientsession(hass)

    auth_payload = {
        "scope": MYSMARTBLINDS_AUTH_SCOPE,
        "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
        "client_id": MYSMARTBLINDS_CLIENT_ID,
        "realm": MYSMARTBLINDS_AUTH_REALM,
        "audience": "",
        "username": username,
        "password": password,
    }
    auth_headers = {
        "User-Agent": MYSMARTBLINDS_USER_AGENT,
        "auth0-client-id": MYSMARTBLINDS_CLIENT_ID,
    }

    try:
        async with session.post(
            MYSMARTBLINDS_AUTH_URL,
            json=auth_payload,
            headers=auth_headers,
        ) as response:
            auth_data = await response.json(content_type=None)
            if response.status >= 400:
                detail = auth_data.get("error_description") or auth_data.get("description") or auth_data.get("error") or response.reason
                raise MySmartBlindsCloudError(f"Authentication failed: {detail}")
    except ClientError as err:
        raise MySmartBlindsCloudError(f"Authentication request failed: {err}") from err

    token = auth_data.get("access_token")
    if not token:
        raise MySmartBlindsCloudError("Authentication succeeded but no access token was returned")

    graphql_headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": MYSMARTBLINDS_USER_AGENT,
        "auth0-client-id": MYSMARTBLINDS_CLIENT_ID,
    }

    try:
        async with session.post(
            MYSMARTBLINDS_GRAPHQL_URL,
            json={"query": MYSMARTBLINDS_QUERY_GET_USER_INFO, "variables": None},
            headers=graphql_headers,
        ) as response:
            graph_data = await response.json(content_type=None)
            if response.status >= 400:
                raise MySmartBlindsCloudError(
                    f"GraphQL request failed: {response.reason}"
                )
    except ClientError as err:
        raise MySmartBlindsCloudError(f"GraphQL request failed: {err}") from err

    if graph_data.get("errors"):
        first_error = graph_data["errors"][0]
        message = first_error.get("message") if isinstance(first_error, dict) else str(first_error)
        raise MySmartBlindsCloudError(f"Cloud API returned an error: {message}")

    user = ((graph_data.get("data") or {}).get("user") or {})
    rooms = {str(room.get("id")): room.get("name") for room in user.get("rooms", []) if not room.get("deleted")}

    blinds: list[CloudBlind] = []
    for blind in user.get("blinds", []):
        if blind.get("deleted"):
            continue
        encoded_mac = blind.get("encodedMacAddress") or ""
        encoded_passkey = blind.get("encodedPasskey") or ""
        try:
            address = decode_mac(encoded_mac)
            key_hex = decode_passkey(encoded_passkey)
        except ValueError as err:
            raise MySmartBlindsCloudError(
                f"Could not decode a blind returned by the cloud API: {err}"
            ) from err
        blinds.append(
            CloudBlind(
                name=blind.get("name") or "MySmartBlinds",
                room_name=rooms.get(str(blind.get("roomId"))),
                encoded_mac=encoded_mac,
                encoded_passkey=encoded_passkey,
                address=address,
                reversed_address=reverse_address(address),
                key_hex=key_hex,
            )
        )
    return blinds


def decode_mac(encoded_mac: str) -> str:
    raw = _decode_base64(encoded_mac)
    if len(raw) != 6:
        raise ValueError("encoded MAC did not decode to 6 bytes")
    return ":".join(f"{part:02X}" for part in raw)


def normalize_mac(address: str) -> str:
    return "".join(char for char in address.upper() if char in "0123456789ABCDEF")


def reverse_address(address: str) -> str:
    normalized = normalize_mac(address)
    if len(normalized) != 12:
        raise ValueError("address did not normalize to 6 bytes")
    pairs = [normalized[index:index + 2] for index in range(0, 12, 2)]
    return ":".join(reversed(pairs))


def mac_matches(candidate: str, target: str) -> bool:
    try:
        normalized_candidate = normalize_mac(candidate)
        normalized_target = normalize_mac(target)
    except Exception:
        return False
    if len(normalized_candidate) != 12 or len(normalized_target) != 12:
        return False
    if normalized_candidate == normalized_target:
        return True
    reversed_candidate = normalize_mac(reverse_address(candidate))
    return reversed_candidate == normalized_target


def decode_passkey(encoded_passkey: str) -> str:
    raw = _decode_base64(encoded_passkey)
    if not raw:
        raise ValueError("encoded passkey was empty")
    return raw.hex()


def _decode_base64(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.b64decode(padded, validate=False)
    except Exception as err:
        raise ValueError("value was not valid base64") from err
