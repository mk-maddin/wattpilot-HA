"""Base entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_IP_ADDRESS,
    STATE_UNKNOWN,
)

from .const import (
    DEFAULT_NAME,
    DOMAIN,
)
from .utils import (
    async_GetChargerProp,
    GetChargerProp,
)

_LOGGER: Final = logging.getLogger(__name__)


class ChargerPlatformEntity(Entity):
    """Base class for Fronius Wattpilot integration."""


    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, entity_cfg, charger) -> None:
        """Initialize the object."""
        try:
            self._charger_id = str(entry.data.get(CONF_FRIENDLY_NAME, entry.data.get(CONF_IP_ADDRESS, DEFAULT_NAME)))
            self._identifier = str(entity_cfg.get('id'))
            _LOGGER.debug("%s - %s: __init__", self._charger_id, self._identifier)
            self._charger = charger
            self._source = entity_cfg.get('source', 'property')
            if self._source == 'attribute' and not hasattr(self._charger, self._identifier):
                _LOGGER.error("%s - %s: __init__: Charger does not have an attribute: %s (maybe a property?)", self._charger_id, self._identifier, self._identifier)
                return None
            elif self._source == 'property' and GetChargerProp(self._charger, self._identifier) is None:
                _LOGGER.error("%s - %s: __init__: Charger does not have a property: %s (maybe an attribute?)", self._charger_id, self._identifier, self._identifier)
                return None
            self._entity_cfg = entity_cfg
            self._entry = entry
            self.hass = hass

            self._name = self._charger_id + ' ' + self._entity_cfg.get('name', self._entity_cfg.get('id'))
            self._icon = self._entity_cfg.get('icon', None)
            self._device_class = self._entity_cfg.get('device_class', None)
            self._unit_of_measurement = self._entity_cfg.get('unit_of_measurement', None)
            self._entity_category = self._entity_cfg.get('entity_category', None)
            self._set_type = self._entity_cfg.get('set_type', None)

            self._attributes = {}
            self._attributes['description'] = self._entity_cfg.get('description', None)
            self._state = STATE_UNKNOWN
           
            self._init_platform_specific()

            self.uniqueid = self._charger_id + "-" + self._entity_cfg.get('uid', self._identifier)
            #_LOGGER.debug("%s - %s: __init__ complete (uid: %s)", self._charger_id, self._identifier, self.uniqueid)
        except Exception as e:            
            _LOGGER.error("%s - %s: __init__ failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    def _init_platform_specific(self): 
        """Platform specific init actions"""
        #do nothing here as this is only a drop-in option for other platforms
        #do not put actions in a try / except block - execeptions should be covered by __init__
        pass


    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self._name


    @property
    def description(self) -> str | None:
        """Return the description of the entity."""
        return self._description


    @property
    def icon(self) -> str | None:
        """Return the icon of the entity"""
        return self._icon


    @property
    def device_class(self) -> str | None:
        """Return the device_class of the entity."""
        return self._device_class


    @property
    def unit_of_measurement(self) -> str | None:
        """Return the unit_of_measurement of the entity."""
        return self._unit_of_measurement


    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity_category of the entity."""
        if not self._entity_category is None:
            return EntityCategory(self._entity_category)
        return None


    @property
    def state(self) -> str | None:
        """Return the current state of the entity."""
        return self._state


    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        return self._attributes


    @property
    def unique_id(self) -> str | None:
        """Return the unique identifier for this entity."""
        return self.uniqueid


    @property
    def available(self) -> bool:
        """Return if device is available."""
        if not getattr(self._charger,'connected', True):
            _LOGGER.debug("%s - %s: available: false because charger disconnected", self._charger_id, self._identifier)
            return False
        elif not getattr(self._charger,'allPropsInitialized', True):
            _LOGGER.debug("%s - %s: available: false because not all properties initialized", self._charger_id, self._identifier)
            return False
        elif self._source == 'attribute' and not hasattr(self._charger, self._identifier):
            _LOGGER.debug("%s - %s: available: false because unknown attribute", self._charger_id, self._identifier)
            return False
        elif self._source == 'property' and async_GetChargerProp(self._charger, self._identifier) is None:
            _LOGGER.debug("%s - %s: available: false because unknown property", self._charger_id, self._identifier)            
            return False
        else:
            return True


    @property
    def should_poll(self) -> bool:
        """Return True if polling is needed."""
        if self._source == 'attribute': 
            return True
        elif self._state == STATE_UNKNOWN:
            return True
        else:
            return False


    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return False if the entity should be disable by default."""
        try:
            enabled = self._entity_cfg.get('enabled', True)
            if enabled == False or str(enabled).lower() == 'false' :
                return False
            return True
        except Exception as e:
            _LOGGER.error("%s - %s: entity_registry_enabled_default failed - default enable: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return True


    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        #_LOGGER.debug("%s - %s: device_info", self._charger_id, self._identifier)
        info = DeviceInfo(
            identifiers={(DOMAIN, getattr(self._charger,'serial', GetChargerProp(self._charger,'sse',None)))},
            default_manufacturer=getattr(self._charger,'manufacturer',STATE_UNKNOWN),
            default_model=GetChargerProp(self._charger,'typ',getattr(self._charger,'devicetype',STATE_UNKNOWN)),
            default_name=getattr(self._charger,'name',getattr(self._charger,'hostname',STATE_UNKNOWN)),
            sw_version=getattr(self._charger,'firmware',STATE_UNKNOWN),
            configuration_url=getattr(self._charger,'url',STATE_UNKNOWN)
        )
        #_LOGGER.debug("%s - %s: device_info result: %s", self._charger_id, self._identifier, info)
        return info


    async def async_update(self) -> None:
        """Async: Get latest data and states for the entity."""
        try:
            if not self.enabled:
                return None
            #_LOGGER.debug("%s - %s: async_update", self._charger_id, self._identifier)
            if self.should_poll:
                _LOGGER.debug("%s - %s: async_update is done via poll - initiate", self._charger_id, self._identifier)
                await self.hass.async_create_task(self.async_local_poll())
            else:
                _LOGGER.debug("%s - %s: async_update is done via push - do nothing / wait for push event", self._charger_id, self._identifier)
        except Exception as e:
            _LOGGER.error("%s - %s: async_update failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    async def _async_update_validate_property(self, state=None): 
        """Async: Validate the given state object, set attributes if necessary and return new single state"""
        try:
            #_LOGGER.debug("%s - %s: _async_update_validate_property", self._charger_id, self._identifier)
            if str(state).startswith('namespace'):
                _LOGGER.debug("%s - %s: _async_update_validate_property: process namespace value", self._charger_id, self._identifier)
                namespace=state
                if self._entity_cfg.get('value_id', None) is None:
                    _LOGGER.error("%s - %s: _async_update_validate_property failed: please specific the 'value_id' to use as state value", self._charger_id, self._identifier) 
                    return None
                state = getattr(namespace,self._entity_cfg.get('value_id',STATE_UNKNOWN),STATE_UNKNOWN)
                _LOGGER.debug("%s - %s: _async_update_validate_property: new state: %s", self._charger_id, self._identifier, state)
                for attr_id in self._entity_cfg.get('attribute_ids', None):
                    _LOGGER.debug("%s - %s: _async_update_validate_property: adding attribute: %s", self._charger_id, self._identifier, attr_id)
                    self._attributes[attr_id] = getattr(namespace,attr_id,STATE_UNKNOWN)
            elif isinstance(state, list):
                _LOGGER.debug("%s - %s: _async_update_validate_property: process list value", self._charger_id, self._identifier)
                state_list=state
                state=state_list[0]
                i=1
                for attr_state in state_list[1:]:
                    self._attributes['state'+str(i)]=attr_state
                    i=i+1
            return state
        except Exception as e:
            _LOGGER.error("%s - %s: _async_update_validate_property failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    async def _async_update_validate_platform_state(self, state=None): 
        """Async: Validate the given state for platform specific requirements"""
        #do nothing here as this is only a drop-in option for other platforms
        #return None if validation failed
        return state


    async def async_local_poll(self) -> None:
        """Async: Poll the latest data and states from the entity."""
        try:
            _LOGGER.debug("%s - %s: async_local_poll", self._charger_id, self._identifier)
            if self._source == 'attribute':
                state = getattr(self._charger,self._identifier,STATE_UNKNOWN)
            elif self._source == 'property':
                state = await async_GetChargerProp(self._charger,self._identifier,STATE_UNKNOWN)
                state = await self._async_update_validate_property(state)
           
            state = await self._async_update_validate_platform_state(state)
            if not state is None:
                self._state = state
                self.async_write_ha_state()
            #_LOGGER.debug("%s - %s: async_local_poll complete: %s", self._charger_id, self._identifier, state)
        except Exception as e:
            _LOGGER.error("%s - %s: async_local_poll failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    async def async_local_push(self, state=None) -> None:
        """Async: Get the latest status from the entity after an update was pushed"""
        try:
            if not self.enabled:
                return None
            _LOGGER.debug("%s - %s: async_local_push", self._charger_id, self._identifier)
            if self._source == 'attribute':
                pass
            elif self._source == 'property':
                state = await self._async_update_validate_property(state)
            
            state = await self._async_update_validate_platform_state(state)
            if not state is None:
                self._state = state
                self.async_write_ha_state()
                #_LOGGER.debug("%s - %s: async_local_push complete: %s", self._charger_id, self._identifier, state)
            else:
                await self.hass.async_create_task(self.async_local_poll())
        except Exception as e:
            _LOGGER.error("%s - %s: async_local_push failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)

