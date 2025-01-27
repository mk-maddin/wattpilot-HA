"""Base entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
from packaging.version import Version

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_IP_ADDRESS,
    CONF_PARAMS,
    STATE_UNKNOWN,
)

from .const import (
    CONF_CONNECTION,
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
    _state_attr='state'

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, entity_cfg, charger) -> None:
        """Initialize the object."""
        try:
            self._charger_id = str(entry.data.get(CONF_FRIENDLY_NAME, entry.data.get(CONF_IP_ADDRESS, DEFAULT_NAME)))
            self._identifier = str(entity_cfg.get('id')).split('_')[0]
            _LOGGER.debug("%s - %s: __init__", self._charger_id, self._identifier)
            
            self._charger = charger
            self._source = entity_cfg.get('source', 'property')
            self._namespace_id = int(entity_cfg.get('namespace_id', 0))
            self._default_state = entity_cfg.get('default_state', None)
            self._entity_cfg = entity_cfg                        
 
            self._entry = entry
            self.hass = hass 
 
            self._init_failed=True
            self._fw_supported = self._check_firmware_supported()
            if not self._fw_supported == True: return None
            self._variant_supported = self._check_variant_supported()
            if not self._variant_supported == True: return None
            self._connection_supported = self._check_connection_supported()
            if not self._connection_supported == True: return None
            
            self._init_failed=False
            if not self._fw_supported == False:
                if self._source == 'attribute' and not hasattr(self._charger, self._identifier):
                    _LOGGER.error("%s - %s: __init__: Charger does not have an attribute: %s (maybe a property?)", self._charger_id, self._identifier, self._identifier)
                    self._init_failed=True
                elif self._source == 'property' and GetChargerProp(self._charger, self._identifier, self._default_state) is None:
                    _LOGGER.error("%s - %s: __init__: Charger does not have a property: %s (maybe an attribute?)", self._charger_id, self._identifier, self._identifier)
                    self._init_failed=True
                elif self._source == 'namespacelist' and GetChargerProp(self._charger, self._identifier, self._default_state)[int(self._namespace_id)] is None:
                    _LOGGER.error("%s - %s: __init__: Charger does not have a namespacelist item: %s[%s]", self._charger_id, self._identifier, self._identifier, self._namespace_id)
                    self._init_failed=True
            if self._init_failed == True: return None
            
            self._attr_name = self._charger_id + ' ' + self._entity_cfg.get('name', self._entity_cfg.get('id'))
            self._attr_icon = self._entity_cfg.get('icon', None)
            self._attr_device_class = self._entity_cfg.get('device_class', None)
            self._entity_category = self._entity_cfg.get('entity_category', None)
            self._set_type = self._entity_cfg.get('set_type', None)

            self._attributes = {}
            self._attributes['description'] = self._entity_cfg.get('description', None)            
            setattr(self, self._state_attr, self._entity_cfg.get('default_state', STATE_UNKNOWN))            

            self._init_platform_specific()

            self._attr_unique_id = self._charger_id + "-" + self._entity_cfg.get('uid', self._entity_cfg.get('id', self._identifier))
            if self._init_failed == True: return None
            #_LOGGER.debug("%s - %s: __init__ complete (uid: %s)", self._charger_id, self._identifier, self._attr_unique_id)
        except Exception as e:            
            _LOGGER.error("%s - %s: __init__ failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    def _init_platform_specific(self): 
        """Platform specific init actions"""
        #do nothing here as this is only a drop-in option for other platforms
        #do not put actions in a try / except block - execeptions should be covered by __init__
        pass


    def _check_firmware_supported(self):
        """Return if the current charger firmware supports this entity"""
        fw_tst=self._entity_cfg.get('firmware', None)
        if fw_tst is None: return True
        fw = getattr(self._charger,'firmware',GetChargerProp(self._charger,'onv', None))
        if fw is None:
            _LOGGER.error("%s - %s: _check_firmware_supported: Cannot identify Charger firmware: %s", self._charger_id, self._identifier, fw)
            return False
        if fw_tst[:2] == '>=':
            v = Version(fw) >= Version(fw_tst[2:])
        elif fw_tst[:2] == '<=':
            v = Version(fw) <= Version(fw_tst[2:])
        elif fw_tst[:2] == '==':
            v = Version(fw) == Version(fw_tst[2:])
        elif fw_tst[:1] == '>':
            v = Version(fw) > Version(fw_tst[1:]) 
        elif fw_tst[:1] == '<':
            v = Version(fw) < Version(fw_tst[1:])            
        else:
            _LOGGER.error("%s - %s: _check_firmware_supported: Invalid firmware version test string: %s", self._charger_id, self._identifier, fw_tst)
            return False
        _LOGGER.debug("%s - %s: _check_firmware_supported complete (%s%s -> %s)", self._charger_id, self._identifier, fw, fw_tst, v)
        return v


    def _check_variant_supported(self):
        """Return if the current charger variant supports this entity"""
        v_tst=self._entity_cfg.get('variant', None)
        if v_tst is None: return True
        variant=GetChargerProp(self._charger,'var',11)
        if str(variant).upper() == str(v_tst).upper(): v=True
        else: v=False
        _LOGGER.debug("%s - %s: _check_variant_supported complete (%s=%s -> %s)", self._charger_id, self._identifier, variant, v_tst, v)
        return v


    def _check_connection_supported(self):
        """Return if the current charger connection type supports this entity"""
        c_tst=self._entity_cfg.get('connection', None)
        if c_tst is None: return True        
        entry_data = self.hass.data[DOMAIN].get(self._entry.entry_id, None)
        if entry_data is None: return True
        config_params = entry_data.get(CONF_PARAMS, None)
        if config_params is None: return True
        connection = config_params.get(CONF_CONNECTION, STATE_UNKNOWN)        
        if str(connection).upper() == str(c_tst).upper(): v=True
        else: v=False
        _LOGGER.debug("%s - %s: _check_connection_supported complete (%s=%s -> %s)", self._charger_id, self._identifier, connection, c_tst, v)
        return v

   
    @property
    def description(self) -> str | None:
        """Return the description of the entity."""
        return self._description


    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity_category of the entity."""
        if not self._entity_category is None:
            return EntityCategory(self._entity_category)
        return None


    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        return self._attributes


    @property
    def available(self) -> bool:
        """Return if device is available."""
        if self._init_failed == True:
            _LOGGER.debug("%s - %s: available: false because enitity init not complete", self._charger_id, self._identifier)            
            return False
        elif self._fw_supported == False:
            _LOGGER.debug("%s - %s: available: false because entity not supported by charger firmware version", self._charger_id, self._identifier)            
            return False
        elif self._variant_supported == False:
            _LOGGER.debug("%s - %s: available: false because entity not supported by charger variant (11kW/22kW)", self._charger_id, self._identifier)            
            return False
        elif self._connection_supported == False:
            _LOGGER.debug("%s - %s: available: false because entity not supported by charger connection type (local/cloud)", self._charger_id, self._identifier)            
            return False            
        elif not getattr(self._charger,'connected', True):
            _LOGGER.debug("%s - %s: available: false because charger disconnected", self._charger_id, self._identifier)
            return False
        elif not getattr(self._charger,'allPropsInitialized', True):
            _LOGGER.debug("%s - %s: available: false because not all properties initialized", self._charger_id, self._identifier)
            return False
        elif self._source == 'attribute' and not hasattr(self._charger, self._identifier):
            _LOGGER.debug("%s - %s: available: false because unknown attribute", self._charger_id, self._identifier)
            return False
        elif self._source == 'property' and GetChargerProp(self._charger, self._identifier, self._default_state) is None:
            _LOGGER.debug("%s - %s: available: false because unknown property", self._charger_id, self._identifier)            
            return False
        elif self._source == 'namespacelist' and GetChargerProp(self._charger, self._identifier, self._default_state)[int(self._namespace_id)] is None:
            _LOGGER.debug("%s - %s: available: false because unknown namespacelist item: %s", self._charger_id, self._identifier, self._namespace_id)            
            return False
        else:
            return True


    @property
    def should_poll(self) -> bool:
        """Return True if polling is needed."""        
        if self._source == 'attribute': 
            return True
        elif self._source == 'namespacelist':
            return True
        elif getattr(self,self._state_attr,STATE_UNKNOWN) == self._entity_cfg.get('default_state', STATE_UNKNOWN):
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
            manufacturer=getattr(self._charger,'manufacturer',STATE_UNKNOWN),
            model=GetChargerProp(self._charger,'typ',getattr(self._charger,'devicetype',STATE_UNKNOWN)),
            name=getattr(self._charger,'name',getattr(self._charger,'hostname',STATE_UNKNOWN)),
            sw_version=getattr(self._charger,'firmware',STATE_UNKNOWN),
            hw_version=str(GetChargerProp(self._charger,'var',STATE_UNKNOWN))+' KW',
        )
        #_LOGGER.debug("%s - %s: device_info result: %s", self._charger_id, self._identifier, info)
        return info


    async def async_update(self) -> None:
        """Async: Get latest data and states for the entity."""
        try:
            if not self.enabled:
                return None
            if not self.available:
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
                #_LOGGER.debug("%s - %s: _async_update_validate_property: new state: %s", self._charger_id, self._identifier, state)
                for attr_id in self._entity_cfg.get('attribute_ids', None):
                    #_LOGGER.debug("%s - %s: _async_update_validate_property: adding attribute: %s", self._charger_id, self._identifier, attr_id)
                    self._attributes[attr_id]=getattr(namespace,attr_id,STATE_UNKNOWN)
            elif isinstance(state, list):
                #_LOGGER.debug("%s - %s: _async_update_validate_property: process list value", self._charger_id, self._identifier)
                state_list=state
                if self._entity_cfg.get('value_id', None) is None:
                    #_LOGGER.debug("%s - %s: _async_update_validate_property: process list value by indexes", self._charger_id, self._identifier)
                    state=state_list[0]
                    i=1
                    for attr_state in state_list[1:]:
                        self._attributes['state'+str(i)]=attr_state
                        i=i+1
                else:
                    #_LOGGER.debug("%s - %s: _async_update_validate_property: process list value by given attributes", self._charger_id, self._identifier)
                    state=state_list[int(self._entity_cfg.get('value_id', 0))]
                    #_LOGGER.debug("%s - %s: _async_update_validate_property: new state: %s", self._charger_id, self._identifier, state)
                    for attr_entry in self._entity_cfg.get('attribute_ids', None):
                        attr_id=attr_entry.split(':')[0]
                        #_LOGGER.debug("%s - %s: _async_update_validate_property: adding attribute: %s", self._charger_id, self._identifier, attr_id)
                        attr_index=attr_entry.split(':')[1]
                        self._attributes[attr_id]=state_list[int(attr_index)]
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
                state = getattr(self._charger,self._identifier,self._default_state)
            elif self._source == 'namespacelist':
                state = await async_GetChargerProp(self._charger,self._identifier,self._default_state)
                state = state[int(self._namespace_id)]
                _LOGGER.debug("%s - %s: async_local_poll namespace pre validate state of %s: %s", self._charger_id, self._identifier, self._attr_unique_id, state)
                state = await self._async_update_validate_property(state)
                _LOGGER.debug("%s - %s: async_local_poll namespace post validate state of %s: %s", self._charger_id, self._identifier, self._attr_unique_id, state)
            elif self._source == 'property':
                state = await async_GetChargerProp(self._charger,self._identifier,self._default_state)
                state = await self._async_update_validate_property(state)
           
            state = await self._async_update_validate_platform_state(state)
            if not state is None:
                setattr(self, self._state_attr, state)
                self.async_write_ha_state()
            #_LOGGER.debug("%s - %s: async_local_poll complete: %s", self._charger_id, self._identifier, state)
        except Exception as e:
            _LOGGER.error("%s - %s: async_local_poll failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    async def async_local_push(self, state=None, initwait=False) -> None:
        """Async: Get the latest status from the entity after an update was pushed"""
        try:
            if not self.enabled:
                return None
            _LOGGER.debug("%s - %s: async_local_push", self._charger_id, self._identifier)
            if self._source == 'attribute':
                pass
            elif self._source == 'namespacelist':
                state = state[int(self._namespace_id)]
                state = await self._async_update_validate_property(state)
            elif self._source == 'property':
                state = await self._async_update_validate_property(state)
            
            state = await self._async_update_validate_platform_state(state)
            if not state is None:
                setattr(self, self._state_attr, state)
                self.async_write_ha_state()
                #_LOGGER.debug("%s - %s: async_local_push complete: %s", self._charger_id, self._identifier, state)
            else:
                await self.hass.async_create_task(self.async_local_poll())                
        except Exception as e:
            if type(e).__name__ == 'NoEntitySpecifiedError' and initwait == False:
                _LOGGER.debug("%s - %s: async_local_push: wait and retry once for setup init delay", self._charger_id, self._identifier)
                await asyncio.sleep(5)
                await self.async_local_push(state,True)
            else:
                _LOGGER.error("%s - %s: async_local_push failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)

