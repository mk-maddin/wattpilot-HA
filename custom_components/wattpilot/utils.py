"""Helper functions for Fronius Wattpilot."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import json
import types

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_IP_ADDRESS,        
    CONF_PARAMS,
    CONF_PASSWORD,
    CONF_TIMEOUT,
)

import wattpilot

from .const import (
    CONF_CHARGER,
    CONF_CONNECTION,
    CONF_CLOUD,
    CONF_DBG_PROPS,
    CONF_LOCAL,
    CONF_PUSH_ENTITIES,
    CONF_SERIAL,
    DEFAULT_NAME,
    DEFAULT_TIMEOUT,
    DOMAIN,
    EVENT_PROPS_ID,
    EVENT_PROPS,
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


async def async_PropertyDebug(identifier: str, value: str, include_properties: bool|list) -> None:
    """Log properties if they change"""
    exclude_properties = ['efh','efh32','efh8','ehs','emhb','fbuf_age','fbuf_pAkku','fbuf_pGrid','fbuf_pPv','fhz','loc','lps','nrg','rbt','rcd','rfb','rssi','tma','tpcm','utc','fbuf_akkuSOC','lpsc','pvopt_averagePAkku','pvopt_averagePGrid','pvopt_averagePPv','pvopt_deltaP']
    if (isinstance(include_properties, list) and identifier in include_properties) or (isinstance(include_properties, bool) and not identifier in exclude_properties):
        _LOGGER.warning("async_PropertyDebug: watch_properties: %s => %s ",identifier,value)


def PropertyUpdateHandler(hass: HomeAssistant, entry_id: str, identifier: str, value: str) -> None:
    """Watches on property updates and executes corresponding action"""
    try:
        #_LOGGER.debug("%s - PropertyUpdateHandler: 'self' execute async", entry_id)
        if entry_id in hass.data[DOMAIN]:
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

        if identifier in EVENT_PROPS:
            charger_id = str(entry_data[CONF_PARAMS].get(CONF_FRIENDLY_NAME, entry_data[CONF_PARAMS].get(CONF_IP_ADDRESS, DEFAULT_NAME)))
            data = {
              "charger_id": charger_id,
              "entry_id": entry_id,
              "property": identifier,
              "value": value
                    }
            hass.bus.fire(EVENT_PROPS_ID,data)

        if entry_data.get(CONF_DBG_PROPS, False):
            hass.async_create_task(async_PropertyDebug(identifier, value, entry_data.get(CONF_DBG_PROPS)))
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
        if charger.allProps[identifier] is None and not default is None:
            return default
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
        if charger.allProps[identifier] is None and not default is None:
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
        if force_type == 'str':
            v=str(value)
        elif str(value).lower() in ["false","true"] or force_type == 'bool':
            v=json.loads(str(value).lower())
        elif str(value).isnumeric() or force_type == 'int':
            v=int(value)
        elif str(value).isdecimal() or force_type == 'float':
            v=float(value)
        elif type(value) is types.SimpleNamespace:
            _LOGGER.warning("%s - async_SetChargerProp: Set for namespace detected - this is untest: %s=%s", DOMAIN, identifier, value)
            v=value.__dict__
        else:
            v=str(value)

        _LOGGER.debug("%s - async_SetChargerProp: Send property update to charger: %s=%s", DOMAIN, identifier, v)
        charger.send_update(identifier,v)
        await asyncio.sleep(0)
        return True
    except Exception as e:
        _LOGGER.error("%s - async_SetChargerProp: Could not set property %s: %s (%s.%s)", DOMAIN, identifier, str(e), e.__class__.__module__, type(e).__name__)
        return False


async def async_GetDataStoreFromDeviceID(hass: HomeAssistant, device_id: str):
    """Async: return the data store for a specific device_id"""
    try:
        _LOGGER.debug("%s - async_GetDataStoreFromDeviceID: receiving device: %s", DOMAIN, device_id)
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)

        _LOGGER.debug("%s - async_GetDataStoreFromDeviceID: get charger data store for config entry", DOMAIN)
        entry_data = None
        for entry_id in device.config_entries:
            if not entry_data is None:
                continue
            entry_data = hass.data[DOMAIN].get(entry_id, None)
            await asyncio.sleep(0)
        if entry_data is None:
            _LOGGER.error("%s - async_GetDataStoreFromDeviceID: Unable to receive data store for device: %s", DOMAIN, device_id)
            return None

        _LOGGER.debug("%s - async_GetDataStoreFromDeviceID: return data_entry", DOMAIN)
        return entry_data
    except Exception as e:
        _LOGGER.error("%s - async_GetDataStoreFromDeviceID: Could not get data store %s: %s (%s.%s)", DOMAIN, device_id, str(e), e.__class__.__module__, type(e).__name__)
        return False


async def async_GetChargerFromDeviceID(hass: HomeAssistant, device_id: str):
    """Async: return the charger object for a specific device_id"""
    try:
        _LOGGER.debug("%s - async_GetChargerFromDeviceID: receiving device: %s", DOMAIN, device_id)
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)

        _LOGGER.debug("%s - async_GetChargerFromDeviceID: get charger object and data store for config entry", DOMAIN)
        charger = None
        for entry_id in device.config_entries:
            if not charger is None:
                continue
            entry_data = hass.data[DOMAIN].get(entry_id, None)
            charger = entry_data.get(CONF_CHARGER, None)
            await asyncio.sleep(0)
        if charger is None:
            _LOGGER.error("%s - async_GetChargerFromDeviceID: Unable to identify charger object for device: %s", DOMAIN, device_id)
            return None

        _LOGGER.debug("%s - async_GetChargerFromDeviceID: return charger object", DOMAIN)
        return charger
    except Exception as e:
        _LOGGER.error("%s - async_GetChargerFromDeviceID: Could not get charger %s: %s (%s.%s)", DOMAIN, device_id, str(e), e.__class__.__module__, type(e).__name__)
        return False


async def async_ConnectCharger(entry_or_device_id, data, charger=None):
    """Async: connect charger and handle connection errors"""
    try:
        con = data.get(CONF_CONNECTION,CONF_LOCAL)
        if charger is None and con == CONF_LOCAL:            
            id = data.get(CONF_IP_ADDRESS, None)
            _LOGGER.debug("%s - async_ConnectCharger: Connecting %s charger by ip: %s", entry_or_device_id, CONF_LOCAL, id)     
            charger=wattpilot.Wattpilot(ip=id, password=data.get(CONF_PASSWORD, None), serial=id, cloud=False)
        elif charger is None and con == CONF_CLOUD:            
            id = data.get(CONF_SERIAL, None)
            _LOGGER.debug("%s - async_ConnectCharger: Connecting %s charger by serial: %s", entry_or_device_id, CONF_CLOUD, id)     
            charger=wattpilot.Wattpilot(ip=id, password=data.get(CONF_PASSWORD, None), serial=id, cloud=True)
        else:
            _LOGGER.debug("%s - async_ConnectCharger: Reconnect existing charger: %s", entry_or_device_id, charger.name)
            id = charger.name
        charger.connect()
    except Exception as e:
        _LOGGER.error("%s - async_ConnectCharger: Connecting charger failed: %s (%s.%s)", entry_or_device_id, str(e), e.__class__.__module__, type(e).__name__)
        return False
    
    try:
        _LOGGER.debug("%s - async_ConnectCharger: Ensure charger is connected and initialized: %s", entry_or_device_id, id)
        timer=0
        timeout=data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        while timeout > timer and not (charger.connected and charger.allPropsInitialized):
            await asyncio.sleep(1)
            timer+=1
        if not charger.connected:
            _LOGGER.error("%s - async_ConnectCharger: Timeout - charger not connected: %s (%s sec)", entry_or_device_id, charger.connected, timeout)
            _LOGGER.error("%s - async_ConnectCharger: Try to restart charger via Wattpilot app", entry_or_device_id)
            return False
        elif not charger.allPropsInitialized: 
            _LOGGER.error("%s - async_ConnectCharger: Timeout - charger not initialized: %s (%s sec)", entry_or_device_id, charger.allPropsInitialized, timeout)
            return False
        elif not timeout > timer:
            _LOGGER.error("%s - async_ConnectCharger: Timeout - unknown reason: %s sec", entry_or_device_id, timeout)
            return False
    except Exception as e:
        _LOGGER.error("%s - async_ConnectCharger: Initialize charger failed: %s (%s.%s)", entry_or_device_id, str(e), e.__class__.__module__, type(e).__name__)
        return False

    _LOGGER.debug("%s - async_ConnectCharger: Charger connected: %s", entry_or_device_id, charger.name)  
    return charger
