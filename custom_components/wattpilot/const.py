"""Constants for Fronius Wattpilot."""

from __future__ import annotations
from typing import Final

DOMAIN: Final = 'wattpilot'
FUNC_OPTION_UPDATES: Final = 'options_update_listener'
SUPPORTED_PLATFORMS: Final = ["sensor", "switch", "select", "number", "button"]

DEFAULT_NAME: Final = 'Wattpilot'
CONF_DBG_PROPS: Final = 'debug_properties'
CONF_CHARGERS: Final = 'chargers'
CONF_CHARGER: Final = 'charger'
CONF_CLOUD_API: Final = 'cloud_api'
CONF_PUSH_ENTITIES: Final = 'push_entities'

DEFAULT_TIMEOUT: Final = 15

EVENT_PROPS_ID: Final = DOMAIN + '_property_message'
EVENT_PROPS: Final = ["ftt", "cak"]

CLOUD_API_URL_PREFIX: Final = 'https://'
CLOUD_API_URL_POSTFIX: Final = '.api.v3.go-e.io/api/'
