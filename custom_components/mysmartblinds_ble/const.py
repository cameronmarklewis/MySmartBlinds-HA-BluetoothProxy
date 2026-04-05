DOMAIN = "mysmartblinds_ble"
PLATFORMS = ["cover"]

DEFAULT_NAME = "MySmartBlinds"
DEFAULT_CLOSE_DIRECTION = "down"
DEFAULT_CONNECTION_TIMEOUT = 15.0
DEFAULT_WRITE_RETRIES = 3
DEFAULT_KEY_DISCOVERY_ATTEMPTS = 256

CONF_ADDRESS = "address"
CONF_KEY = "key"
CONF_CLOSE_DIRECTION = "close_direction"
CONF_CONNECTION_TIMEOUT = "connection_timeout"
CONF_WRITE_RETRIES = "write_retries"
CONF_SETUP_METHOD = "setup_method"
CONF_KEY_SOURCE = "key_source"
CONF_DISCOVERY_ATTEMPTS = "discovery_attempts"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CLOUD_BLIND = "cloud_blind"

OPTION_AUTO = "auto"
OPTION_CLOUD = "cloud"
OPTION_MANUAL = "manual"

KEY_SOURCE_AUTO = "auto"
KEY_SOURCE_CLOUD = "cloud"
KEY_SOURCE_MANUAL = "manual"

SERVICE_DISCOVER_KEY = "discover_key"
SERVICE_SCAN_DEVICES = "scan_devices"
SERVICE_PING = "ping"

ATTR_DISCOVERED_KEY = "discovered_key"
ATTR_ATTEMPTS = "attempts"
ATTR_DEVICES = "devices"
ATTR_RSSI = "rssi"
ATTR_NAME = "name"
ATTR_LAST_ERROR = "last_error"
ATTR_KEY_SOURCE = "key_source"

UUID_KEY = "00001409-1212-efde-1600-785feabcd123"
UUID_SET = "0000140b-1212-efde-1600-785feabcd123"

HANDLE_KEY = 0x001B
HANDLE_SET = 0x001F

MAX_NATIVE_POSITION = 200
MID_NATIVE_POSITION = 100
MIN_NATIVE_POSITION = 0

DISCOVER_KEY_MAX = 255
KNOWN_LOCAL_NAMES = {"SmartBlind_DFU", "SmartBlind", "MySmartBlinds"}

MYSMARTBLINDS_AUTH_DOMAIN = "mysmartblinds.auth0.com"
MYSMARTBLINDS_CLIENT_ID = "1d1c3vuqWtpUt1U577QX5gzCJZzm8WOB"
MYSMARTBLINDS_GRAPHQL_URL = "https://api.mysmartblinds.com/v1/graphql"
MYSMARTBLINDS_AUTH_URL = f"https://{MYSMARTBLINDS_AUTH_DOMAIN}/oauth/token"
MYSMARTBLINDS_AUTH_SCOPE = "openid email offline_access"
MYSMARTBLINDS_AUTH_REALM = "Username-Password-Authentication"
MYSMARTBLINDS_USER_AGENT = "MySmartBlinds/2.3.3 (iPhone; iOS 14.2; Scale/2.00"

MYSMARTBLINDS_QUERY_GET_USER_INFO = """
query GetUserInfo {
  user {
    rooms {
      id
      name
      deleted
    }
    blinds {
      name
      encodedMacAddress
      encodedPasskey
      roomId
      deleted
    }
  }
}
"""


CLOUD_CACHE_STORE_KEY = "mysmartblinds_ble_cloud_cache"
CLOUD_CACHE_VERSION = 1
