"""Helper functions for Fronius Wattpilot."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import json

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    CONF_PARAMS,
)

from .const import (
    CONF_DBG_PROPS,
    CONF_PUSH_ENTITIES,
    DOMAIN,
)

_LOGGER: Final = logging.getLogger(__name__)

async def async_ProgrammingDebug(obj, show_all:bool=False) -> None:
    """Async: return all attributes of a specific objec""" 
    try:
        _LOGGER.debug("%s - async_ProgrammingDebug: %s", DOMAIN, obj)
        for attr in dir(obj):
            if attr.startswith('_') and not show_all:
                continue
            if hasattr(obj, attr ):
                _LOGGER.debug("%s - async_ProgrammingDebug: %s = %s", DOMAIN, attr, getattr(obj, attr))
            await asyncio.sleep(0)
    except Exception as e:
        _LOGGER.error("%s - async_ProgrammingDebug: failed: %s (%s.%s)", DOMAIN, str(e), e.__class__.__module__, type(e).__name__)
        pass

def ProgrammingDebug(obj, show_all:bool=False) -> None:
    """return all attributes of a specific objec"""
    try:
        _LOGGER.debug("%s - ProgrammingDebug: %s", DOMAIN, obj)
        for attr in dir(obj):
            if attr.startswith('_') and not show_all:
                continue
            if hasattr(obj, attr ):
                _LOGGER.debug("%s - ProgrammingDebug: %s = %s", DOMAIN, attr, getattr(obj, attr))
    except Exception as e:
        _LOGGER.error("%s - ProgrammingDebug: failed: %s (%s.%s)", DOMAIN, str(e), e.__class__.__module__, type(e).__name__)
        pass

async def async_PropertyDebug(identifier: str, value: str) -> None:
    """Log properties if they change"""
    exclude_properties = ['efh','efh32','efh8','ehs','emhb','fbuf_age','fbuf_pAkku','fbuf_pGrid','fbuf_pPv','fhz','loc','lps','nrg','rbt','rcd','rfb','rssi','tma','tpcm','utc','fbuf_akkuSOC','lpsc','pvopt_averagePAkku','pvopt_averagePGrid','pvopt_averagePPv','pvopt_deltaP']
    if not identifier in exclude_properties:
        _LOGGER.warning("async_PropertyDebug: watch_properties: %s => %s ",identifier,value)

def PropertyUpdateHandler(hass: HomeAssistant, entry_id: str, identifier: str, value: str) -> None:
    """Watches on property updates and executes corresponding action"""
    try:
        #_LOGGER.debug("%s - PropertyUpdateHandler: 'self' execute async", entry_id)
        asyncio.run_coroutine_threadsafe(async_PropertyUpdateHandler(hass, entry_id, identifier, value), hass.loop)
    except Exception as e:
        _LOGGER.error("%s - PropertyUpdateHandler: Could not 'self' execute async: %s (%s.%s)", entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return default

async def async_PropertyUpdateHandler(hass: HomeAssistant, entry_id: str, identifier: str, value: str) -> None:
    """Asnyc: Watches on property updates and executes corresponding action"""
    try:
        #_LOGGER.debug("%s - async_PropertyUpdateHandler: get entry_data", entry_id)
        entry_data=hass.data[DOMAIN][entry_id]
       
        entity=entry_data[CONF_PUSH_ENTITIES].get(identifier, None)
        if not entity is None:
            hass.async_create_task(entity.async_local_push(value))
        
        if entry_data[CONF_PARAMS].get(CONF_DBG_PROPS,False):
            hass.async_create_task(async_PropertyDebug(identifier, value))
    except Exception as e:
        _LOGGER.error("%s - PropertyUpdateHandler: Could not 'self' execute async: %s (%s.%s)", entry_id, str(e), e.__class__.__module__, type(e).__name__)
        return default

async def async_GetChargerProp(charger, identifier: str, default=None):
    """Async: return the value of a charger attribute"""
    try:
        if not hasattr(charger, 'allProps'):
            _LOGGER.error("%s - async_GetChargerProp: Charger does not have allProps attribute: %s", DOMAIN, charger)
            return default
        if identifier is None or not identifier in charger.allProps: 
            _LOGGER.error("%s - async_GetChargerProp: Charger does not have property: %s", DOMAIN, identifier)
            return default
        await asyncio.sleep(0)
        return charger.allProps[identifier]
    except Exception as e:
        _LOGGER.error("%s - async_GetChargerProp: Could not get property %s: %s (%s.%s)", DOMAIN, identifier, str(e), e.__class__.__module__, type(e).__name__)
        return default

def GetChargerProp(charger, identifier:str=None, default:str=None):
    """return the value of a charger attribute"""
    try:
        if not hasattr(charger, 'allProps'):
            _LOGGER.error("%s - GetChargerProp: Charger does not have allProps attribute: %s", DOMAIN, charger)
            return default
        if identifier is None or not identifier in charger.allProps:
            _LOGGER.error("%s - GetChargerProp: Charger does not have property: %s", DOMAIN, identifier)
            return default
        return charger.allProps[identifier]
    except Exception as e:
        _LOGGER.error("%s - GetChargerProp: Could not get property %s: %s (%s.%s)", DOMAIN, identifier, str(e), e.__class__.__module__, type(e).__name__)
        return default

async def async_SetChargerProp(charger, identifier:str=None, value:str=None, force:bool=False, force_type:str=None) -> bool:
    """Async: set the value of a charger attribute"""
    try:
        if not hasattr(charger, 'allProps'):
            _LOGGER.error("%s - async_SetChargerProp: Charger does not have allProps attribute: %s", DOMAIN, charger)
            return False
        if identifier is None:
            _LOGGER.error("%s - async_SetChargerProp: Charger property name has to be defined: %s", DOMAIN, identifier)
            return False
        if not identifier in charger.allProps and not force:
            _LOGGER.error("%s - async_SetChargerProp: Charger does not have property: %s", DOMAIN, identifier)
            return False
        if value is None:
            _LOGGER.error("%s - async_SetChargerProp: A value parameter is required: %s=%s", DOMAIN, identifier, value)
            return False
      
        if not force_type == None:
            force_type=str(force_type).lower()

        _LOGGER.debug("%s - async_SetChargerProp: Prepare new property value: %s=%s", DOMAIN, identifier, value)
        if str(value).lower() in ["false","true"] or force_type == 'bool':
            v=json.loads(str(value).lower())
        elif str(value).isnumeric() or force_type == 'int':
            v=int(value)
        elif str(value).isdecimal() or force_type == 'float':
            v=float(value)
        else:
            v=str(value)

        _LOGGER.debug("%s - async_SetChargerProp: Send property update to charger: %s=%s", DOMAIN, identifier, v)
        charger.send_update(identifier,v)
        await asyncio.sleep(0)
        return True
    except Exception as e:
        _LOGGER.error("%s - async_SetChargerProp: Could not set property %s: %s (%s.%s)", DOMAIN, identifier, str(e), e.__class__.__module__, type(e).__name__)
        return False

