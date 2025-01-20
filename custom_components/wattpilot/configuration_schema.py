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
from homeassistant.helpers.selector import (
    SelectSelector, 
    SelectSelectorConfig,
)
import homeassistant.helpers.config_validation as cv


from .const import (
    CONF_CONNECTION,
    CONF_CLOUD,
    CONF_LOCAL,
    CONF_SERIAL,
    DEFAULT_NAME,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER: Final = logging.getLogger(__name__)

CONNECTION_SCHEMA: Final = vol.Schema({
    vol.Required(CONF_CONNECTION, default=CONF_LOCAL): SelectSelector(SelectSelectorConfig(options=[CONF_LOCAL, CONF_CLOUD])),
})


LOCAL_SCHEMA: Final = vol.Schema({
    vol.Required(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_IP_ADDRESS, default=None): cv.string,
    vol.Required(CONF_PASSWORD, default=None): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})


CLOUD_SCHEMA: Final = vol.Schema({
    vol.Required(CONF_FRIENDLY_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_SERIAL, default=None): cv.string,
    vol.Required(CONF_PASSWORD, default=None): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
})


async def async_get_OPTIONS_LOCAL_SCHEMA(current_data):
    """Async: return an schema object with current values as default""" 
    try:
        _LOGGER.debug("%s - async_get_OPTIONS_LOCAL_SCHEMA", DOMAIN)
        OPTIONS_LOCAL_SCHEMA: Final = vol.Schema({
            vol.Required(CONF_FRIENDLY_NAME, default=current_data.get(CONF_FRIENDLY_NAME,DEFAULT_NAME)): cv.string,
            vol.Required(CONF_IP_ADDRESS, default=current_data.get(CONF_IP_ADDRESS,None)): cv.string,
            vol.Required(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD,None)): cv.string,
            vol.Optional(CONF_TIMEOUT, default=current_data.get(CONF_TIMEOUT,DEFAULT_TIMEOUT)): cv.positive_int,
        })
        await asyncio.sleep(0)
        return OPTIONS_LOCAL_SCHEMA
    except Exception as e:
        _LOGGER.error("%s - async_get_OPTIONS_LOCAL_SCHEMA: failed: %s (%s.%s)", DOMAIN, str(e), e.__class__.__module__, type(e).__name__)
        return LOCAL_SCHEMA


async def async_get_OPTIONS_CLOUD_SCHEMA(current_data):
    """Async: return an schema object with current values as default""" 
    try:
        _LOGGER.debug("%s - async_get_OPTIONS_CLOUD_SCHEMA", DOMAIN)
        OPTIONS_CLOUD_SCHEMA: Final = vol.Schema({
            vol.Required(CONF_FRIENDLY_NAME, default=current_data.get(CONF_FRIENDLY_NAME,DEFAULT_NAME)): cv.string,
            vol.Required(CONF_SERIAL, default=current_data.get(CONF_SERIAL,None)): cv.string,
            vol.Required(CONF_PASSWORD, default=current_data.get(CONF_PASSWORD,None)): cv.string,
            vol.Optional(CONF_TIMEOUT, default=current_data.get(CONF_TIMEOUT,DEFAULT_TIMEOUT)): cv.positive_int,
        })
        await asyncio.sleep(0)
        return OPTIONS_CLOUD_SCHEMA
    except Exception as e:
        _LOGGER.error("%s - async_get_OPTIONS_CLOUD_SCHEMA: failed: %s (%s.%s)", DOMAIN, str(e), e.__class__.__module__, type(e).__name__)
        return CLOUD_SCHEMA
