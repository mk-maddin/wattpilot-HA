"""Diagnostics support for the Fronius Wattpilot integration."""

from __future__ import annotations
from importlib_metadata import version
from typing import (
    Final,
    Any,
)
import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
)

from .const import (
    CONF_CHARGER,
    CONF_DBG_PROPS,
    DOMAIN,
)

REDACT_CONFIG = {CONF_IP_ADDRESS, CONF_PASSWORD}
REDACT_ALLPROPS = {'wifis', 'scan', 'data', 'dll', 'cak', 'ocppck', 'ocppcc', 'ocppsc' }

_LOGGER: Final = logging.getLogger(__name__)
platform='diagnostics'

async def async_get_config_entry_diagnostics( hass: HomeAssistant, entry: ConfigEntry ) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    _LOGGER.debug("Returning %s platform entry: %s", platform, entry.entry_id)
    try:
        _LOGGER.debug("%s - async_get_config_entry_diagnostics %s: Getting charger instance from data store", entry.entry_id, platform)
        charger=hass.data[DOMAIN][entry.entry_id][CONF_CHARGER]
    except Exception as e:
        _LOGGER.error("%s - async_get_config_entry_diagnostics %s: Getting charger instance from data store failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return False  
    
    try:
        _LOGGER.debug("%s - async_get_config_entry_diagnostics %s: Add config entry configuration to output", entry.entry_id, platform)
        diag: dict[str, Any] = { "config": async_redact_data(entry.as_dict(), REDACT_CONFIG) }
    except Exception as e:
        _LOGGER.error("%s - async_get_config_entry_diagnostics %s: Adding config entry configuration to output failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_get_config_entry_diagnostics %s: Add charger properties to output", entry.entry_id, platform)
        diag["charger_properties"] = async_redact_data(charger.allProps, REDACT_ALLPROPS)
    except Exception as e:
        _LOGGER.error("%s - async_get_config_entry_diagnostics %s: Adding charger properties to output failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return diag

    try:
        _LOGGER.debug("%s - async_get_config_entry_diagnostics %s: Add python modules version", entry.entry_id, platform)
        diag["wattpilot_module"] = version('wattpilot')
        diag["pyyaml_module"] = version('pyyaml')
        diag["importlib_metadata_module"] = version('importlib_metadata')
        diag["aiofiles_module"] = version('aiofiles')
        diag["packaging"] = version('packaging')
    except Exception as e:
        _LOGGER.error("%s - async_get_config_entry_diagnostics %s: Add python modules version failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return diag

    return diag
