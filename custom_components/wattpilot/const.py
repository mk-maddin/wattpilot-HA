"""Constants for Fronius Wattpilot."""

from __future__ import annotations
from typing import Final

DOMAIN: Final = 'wattpilot'
FUNC_OPTION_UPDATES: Final = 'options_update_listener'
FUNC_PROPERTY_UPDATES_CALLBACK: Final = 'property_updates_callback'
SUPPORTED_PLATFORMS: Final = ["button", "number", "select", "sensor", "switch", "update"]

DEFAULT_NAME: Final = 'Wattpilot'
CONF_DBG_PROPS: Final = 'debug_properties'
CONF_CHARGERS: Final = 'chargers'
CONF_CHARGER: Final = 'charger'
CONF_CLOUD_API: Final = 'cloud_api'
CONF_CLOUD: Final = 'cloud'
CONF_CONNECTION: Final = 'connection'
CONF_LOCAL: Final = 'local'
CONF_PUSH_ENTITIES: Final = 'push_entities'
CONF_SERIAL: Final = 'serial'

DEFAULT_TIMEOUT: Final = 15

EVENT_PROPS_ID: Final = DOMAIN + '_property_message'
EVENT_PROPS: Final = ["ftt", "cak"]

CLOUD_API_URL_PREFIX: Final = 'https://'
CLOUD_API_URL_POSTFIX: Final = '.api.v3.go-e.io/api/'
