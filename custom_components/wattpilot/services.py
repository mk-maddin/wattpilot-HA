"""Support for dScriptModule services."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import functools

import time
import datetime

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import (
        CONF_DEVICE_ID,
        CONF_TRIGGER_TIME,
        CONF_API_KEY,
        CONF_EXTERNAL_URL,
)

from .const import (
    CONF_CLOUD_API,
    CONF_DBG_PROPS,
    CLOUD_API_URL_PREFIX,
    CLOUD_API_URL_POSTFIX,    
    DOMAIN,
)
from .utils import (
    async_GetChargerProp,
    async_GetChargerFromDeviceID,
    async_GetDataStoreFromDeviceID,
    async_ProgrammingDebug,
    async_SetChargerProp,
)

_LOGGER: Final = logging.getLogger(__name__)


async def async_registerService(hass: HomeAssistant, name:str , service) -> None:
    """Register a service if it does not already exist"""
    try:
        _LOGGER.debug("%s - async_registerService: %s", DOMAIN, name)
        await asyncio.sleep(0)        
        if not hass.services.has_service(DOMAIN, name):
            #_LOGGER.info("%s - async_registerServic: register service: %s", DOMAIN, name)
            #hass.services.async_register(DOMAIN, name, service)
            hass.services.async_register(DOMAIN, name, functools.partial(service, hass))
        else:
            _LOGGER.debug("%s - async_registerServic: service already exists: %s", DOMAIN, name)  
    except Exception as e:
        _LOGGER.error("%s - async_registerService: failed: %s (%s.%s)", DOMAIN, str(e), e.__class__.__module__, type(e).__name__)        


async def async_service_SetNextTrip(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to set the next trip timestamp"""
    try:
        device_id = call.data.get(CONF_DEVICE_ID, None)
        trigger_time = call.data.get(CONF_TRIGGER_TIME, None)
        if device_id is None:
            _LOGGER.error("%s - async_service_SetNextTrip: %s is a required parameter", DOMAIN, CONF_DEVICE_ID)
            return None
        elif trigger_time is None: 
            _LOGGER.error("%s - async_service_SetNextTrip: %s is a required parameter", DOMAIN, CONF_TRIGGER_TIME)
            return None

        _LOGGER.debug("%s - async_service_SetNextTrip: get charger for device_id: %s", DOMAIN, device_id)
        charger = await async_GetChargerFromDeviceID(hass, device_id)
        if charger is None:
            return None

        _LOGGER.debug("%s - async_service_SetNextTrip: trigger time: %s", DOMAIN, trigger_time)
        timestamp = int(time.mktime(datetime.datetime.strptime("1970-01-01 "+trigger_time, "%Y-%m-%d %H:%M:%S").timetuple()))

        _LOGGER.debug("%s - async_service_SetNextTrip: validate daylight saving", DOMAIN)
        tds = await async_GetChargerProp(charger,'tds')
        if int(tds) == 1:
            _LOGGER.debug("%s - async_service_SetNextTrip: apply daylight saving time", DOMAIN)
            timestamp = timestamp + 3600

        _LOGGER.debug("%s - async_service_SetNextTrip: set nexttrip timesamp %s for charger: %s", DOMAIN, charger.name)
        await async_SetChargerProp(charger,'ftt',timestamp)

    except Exception as e:
        _LOGGER.error("%s - async_service_SetNextTrip: %s failed: %s (%s.%s)", DOMAIN, call, str(e), e.__class__.__module__, type(e).__name__)


async def async_service_SetGoECloud(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to set the next trip timestamp"""
    try:
        device_id = call.data.get(CONF_DEVICE_ID, None)
        api_state= call.data.get(CONF_CLOUD_API, None)
        if device_id is None:
            _LOGGER.error("%s - async_service_SetGoECloud: %s is a required parameter", DOMAIN, CONF_DEVICE_ID)
            return None
        elif api_state is None: 
            _LOGGER.error("%s - async_service_SetGoECloud: %s is a required parameter", DOMAIN, CONF_CLOUD_API)
            return None
        _LOGGER.debug("%s - async_service_SetGoECloud: service call data: %s", DOMAIN, call.data)

        _LOGGER.debug("%s - async_service_SetGoECloud: get entry_data for device_id: %s", DOMAIN, device_id)
        entry_data = await async_GetDataStoreFromDeviceID(hass, device_id)
        if entry_data is None:
            return None

        _LOGGER.debug("%s - async_service_SetGoECloud: get charger for device_id: %s", DOMAIN, device_id)
        charger = await async_GetChargerFromDeviceID(hass, device_id)
        if charger is None:
            return None

        if api_state == True:
            _LOGGER.debug("%s - async_service_SetGoECloud: Enabling cloud api", DOMAIN)
            if not await async_SetChargerProp(charger,'cae',True):
                return False
            timer=0
            timeout=10
            while timeout > timer and (charger.cak == '' or charger.cak is None):
                await asyncio.sleep(1)
                timer+=1
            if not timeout > timer:
                _LOGGER.error("%s - async_service_SetGoECloud: Timeout - api key not available after: %s sec", DOMAIN, timeout)
                entry_data[CONF_API_KEY]=False
                return None

            _LOGGER.debug("%s - async_service_SetGoECloud: Saving api key to data store", DOMAIN)
            entry_data[CONF_API_KEY]=charger.cak
            _LOGGER.info("%s - async_service_SetGoECloud: %s cloud API KEY: %s", DOMAIN, charger.name, entry_data[CONF_API_KEY])

            serial = getattr(charger,'serial', await async_GetChargerProp(charger,'sse',False))
            if serial:
                entry_data[CONF_EXTERNAL_URL]=CLOUD_API_URL_PREFIX + serial + CLOUD_API_URL_POSTFIX
                _LOGGER.info("%s - async_service_SetGoECloud: %s cloud API URL: %s", DOMAIN, charger.name, entry_data[CONF_EXTERNAL_URL])
        else:
            _LOGGER.debug("%s - async_service_SetGoECloud: %s disabling cloud api", DOMAIN, charger.name)
            entry_data[CONF_API_KEY]=False
            await async_SetChargerProp(charger,'cae',False)
            _LOGGER.info("%s - async_service_SetGoECloud: %s DISABLED cloud API", DOMAIN, charger.name)

    except Exception as e:
        _LOGGER.error("%s - async_service_SetGoECloud: %s failed: %s (%s.%s)", DOMAIN, call, str(e), e.__class__.__module__, type(e).__name__)


async def async_service_SetDebugProperties(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service to enable/disable charger properties debugging"""
    try:
        device_id = call.data.get(CONF_DEVICE_ID, None)
        dbg_state= call.data.get(CONF_DBG_PROPS, None)
        if device_id is None:
            _LOGGER.error("%s - async_service_SetDebugProperties: %s is a required parameter", DOMAIN, CONF_DEVICE_ID)
            return None
        elif dbg_state is None: 
            _LOGGER.error("%s - async_service_SetDebugProperties: %s is a required parameter", DOMAIN, CONF_DBG_PROPS)
            return None

        _LOGGER.debug("%s - async_service_SetDebugProperties: get entry_data for device_id: %s", DOMAIN, device_id)
        entry_data = await async_GetDataStoreFromDeviceID(hass, device_id)
        if entry_data is None:
            _LOGGER.warning("%s - async_service_SetDebugProperties: unable to get entry_data for: %s", DOMAIN, CONF_DEVICE_ID)
            return None

        if isinstance(dbg_state, bool):
            entry_data[CONF_DBG_PROPS] = dbg_state
        elif isinstance(dbg_state, str) and dbg_state.lower() == 'true':
            entry_data[CONF_DBG_PROPS] = True
        elif isinstance(dbg_state, str) and dbg_state.lower() == 'false':
            entry_data[CONF_DBG_PROPS] = False
        elif isinstance(dbg_state, list):
            entry_data[CONF_DBG_PROPS] = dbg_state
        else:
            _LOGGER.error("%s - async_service_SetDebugProperties: invalid debug state: %s (%s)", DOMAIN, dbg_state, type(dbg_state))
            return None

    except Exception as e:
        _LOGGER.error("%s - async_service_SetDebugProperties: %s failed: %s (%s.%s)", DOMAIN, call, str(e), e.__class__.__module__, type(e).__name__)

