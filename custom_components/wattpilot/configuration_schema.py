"""Configuration schema for Fronius Wattpilot."""

from typing import Final
import logging
import asyncio
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_TIMEOUT,
)
import homeassistant.helpers.config_validation as cv

from .const import (
    DEFAULT_TIMEOUT,
    DOMAIN,
)

#_LOGGER: Final = logging.getLogger(__name__)

CHARGER_SCHEMA: Final = vol.Schema({
    vol.Required(CONF_FRIENDLY_NAME, default="Wattpilot"): cv.string,
    vol.Required(CONF_IP_ADDRESS, default="192.168.1.123"): cv.string,
    vol.Required(CONF_PASSWORD, default='12345678ABCD'): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})

