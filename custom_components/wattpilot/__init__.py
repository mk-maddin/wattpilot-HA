"""Init for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PARAMS,
    CONF_PASSWORD,
    CONF_TIMEOUT,
)

import wattpilot

from .const import (
    CONF_CHARGER,
    CONF_DBG_PROPS,
    CONF_PUSH_ENTITIES,
    DEFAULT_TIMEOUT,
    DOMAIN,
    FUNC_OPTION_UPDATES,
    SUPPORTED_PLATFORMS,
)
from .services import (
    async_registerService,
    async_service_SetDebugProperties,
    async_service_SetGoECloud,
    async_service_SetNextTrip,
)
from .utils import (
    async_ProgrammingDebug,
    async_SetChargerProp,
    PropertyUpdateHandler,
)

_LOGGER: Final = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a charger from the config entry."""
    _LOGGER.debug("Setting up config entry: %s", entry.entry_id)

    try:
        ip = entry.data.get(CONF_IP_ADDRESS, None)
        _LOGGER.debug("%s - async_setup_entry: Connecting charger ip: %s", entry.entry_id, ip)     
        charger=wattpilot.Wattpilot(ip, entry.data.get(CONF_PASSWORD, None))
        charger.connect()
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: Connecting charger ip failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False
    
    try:
        _LOGGER.debug("%s - async_setup_entry: Ensure charger is connected and initialized: %s", entry.entry_id, ip)
        timer=0
        timeout=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        while timeout > timer and not (charger.connected and charger.allPropsInitialized):
            await asyncio.sleep(1)
            timer+=1
        if not charger.connected:
            _LOGGER.error("%s - async_setup_entry: Timeout - charger not connected: %s (%s sec)", entry.entry_id, charger.connected, timeout)
            return False
        elif not charger.allPropsInitialized: 
            _LOGGER.error("%s - async_setup_entry: Timeout - charger not initialized: %s (%s sec)", entry.entry_id, charger.allPropsInitialized, timeout)
            return False
        elif not timeout > timer:
            _LOGGER.error("%s - async_setup_entry: Timeout - unknown reason: %s sec", entry.entry_id, timeout)
            return False
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: Initialize charger failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: Creating data store: %s.%s ", entry.entry_id, DOMAIN, entry.entry_id)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault(entry.entry_id, {})
        entry_data=hass.data[DOMAIN][entry.entry_id]
        entry_data[CONF_CHARGER]=charger
        entry_data[CONF_PARAMS]=entry.data
        entry_data[CONF_DBG_PROPS]=False
        entry_data.setdefault(CONF_PUSH_ENTITIES, {})
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: Creating data store failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: Register option updates listener: %s ", entry.entry_id, FUNC_OPTION_UPDATES)
        entry_data[FUNC_OPTION_UPDATES] = entry.add_update_listener(options_update_listener) 
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: Register option updates listener failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: Trigger setup for platforms", entry.entry_id)
        await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: Setup trigger failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: register properties update handler", entry.entry_id)
        charger.register_property_callback(lambda identifier, value: PropertyUpdateHandler(hass, entry.entry_id, identifier, value))
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: Cloud not register properties updater handler: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry: register services", entry.entry_id)
        await async_registerService(hass, "set_goe_cloud", async_service_SetGoECloud)
        await async_registerService(hass, "set_debug_properties", async_service_SetDebugProperties)
        await async_registerService(hass, "set_next_trip", async_service_SetNextTrip)        
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry: register services failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False 

    _LOGGER.debug("%s - async_setup_entry: Completed", entry.entry_id)
    return True

async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle options update."""
    _LOGGER.debug("Update options / relaod config entry: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        _LOGGER.debug("Unloading config entry: %s", entry.entry_id)
        all_ok = True
        for platform in SUPPORTED_PLATFORMS:
            _LOGGER.debug("%s - async_unload_entry: unload platform: %s", entry.entry_id, platform)
            platform_ok = await asyncio.gather(*[hass.config_entries.async_forward_entry_unload(entry, platform)])

            if not platform_ok:
                _LOGGER.error("%s - async_unload_entry: failed to unload: %s (%s)", entry.entry_id, platform, platform_ok)
                all_ok = platform_ok

        if all_ok:
            _LOGGER.debug("%s - async_unload_entry: Unload option updates listener: %s.%s ", entry.entry_id, FUNC_OPTION_UPDATES)
            hass.data[DOMAIN][entry.entry_id][FUNC_OPTION_UPDATES]()
        
            _LOGGER.debug("%s - async_unload_entry: Remove data store: %s.%s ", entry.entry_id, DOMAIN, entry.entry_id)
            hass.data[DOMAIN].pop(entry.entry_id)
        return all_ok
    except Exception as e:
        _LOGGER.error("%s - async_unload_entry: Unload device failed: %s (%s.%s)", entry.entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

