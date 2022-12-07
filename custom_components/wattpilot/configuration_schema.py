"""Configuration schema for Fronius Wattpilot."""

from __future__ import annotations
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
    DEFAULT_NAME,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER: Final = logging.getLogger(__name__)

CHARGER_SCHEMA: Final = vol.Schema({
    vol.Required(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_IP_ADDRESS, default=None): cv.string,
    vol.Required(CONF_PASSWORD, default=None): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})

async def async_get_OPTIONS_CHARGER_SCHEMA(current_data):
    """Async: return an schema object with current values as default""" 
    try:
        _LOGGER.debug("%s - async_get_OPTIONS_CHARGER_SCHEMA", DOMAIN)
        OPTIONS_CHARGER_SCHEMA: Final = vol.Schema({
            vol.Required(CONF_FRIENDLY_NAME, default=current_data.get(CONF_FRIENDLY_NAME,DEFAULT_NAME)): cv.string,
            vol.Required(CONF_IP_ADDRESS, default=current_data.get(CONF_IP_ADDRESS)): cv.string,
            vol.Required(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD)): cv.string,
            vol.Optional(CONF_TIMEOUT, default=current_data.get(CONF_TIMEOUT,DEFAULT_TIMEOUT)): cv.positive_int,
        })
        await asyncio.sleep(0)
        return OPTIONS_CHARGER_SCHEMA
    except Exception as e:
        _LOGGER.error("%s - async_get_OPTIONS_CHARGER_SCHEMA: failed: %s (%s.%s)", DOMAIN, str(e), e.__class__.__module__, type(e).__name__)
        return CHARGER_SCHEMA