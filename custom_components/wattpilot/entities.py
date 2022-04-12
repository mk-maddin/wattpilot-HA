"""Base entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio

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


    def __init__(self, entry: ConfigEntry, entity_cfg, charger) -> None:
        """Initialize the object."""
        try:
            self._charger_id = str(entry.data.get(CONF_FRIENDLY_NAME, entry.data.get(CONF_IP_ADDRESS, DEFAULT_NAME)))
            self._identifier = str(entity_cfg.get('id'))
            _LOGGER.debug("%s - %s: __init__", self._charger_id, self._identifier)
            self._charger = charger
            self._source = entity_cfg.get('source', 'property')
            if self._source == 'attribute' and not hasattr(self._charger, self._identifier):
                _LOGGER.error("%s - %s: __init__: Charger does not have an attributed: %s (maybe a property?)", self._charger_id, self._identifier, self._identifier)
                return None
            elif self._source == 'property' and GetChargerProp(self._charger, self._identifier) is None:
                _LOGGER.error("%s - %s: __init__: Charger does not have a property: %s (maybe an attribute?)", self._charger_id, self._identifier, self._identifier)
                return None
            self._entity_cfg = entity_cfg
            self._entry = entry
        
            self._name = self._charger_id + ' ' + self._entity_cfg.get('name', self._entity_cfg.get('id'))
            self._icon = self._entity_cfg.get('icon', None)
            self._device_class = self._entity_cfg.get('device_class', None)
            self._unit_of_measurement = self._entity_cfg.get('unit_of_measurement', None)
            self._entity_category = self._entity_cfg.get('entity_category', None)
            
            self._attributes = {}
            self._attributes['description'] = self._entity_cfg.get('description', None)
            self._state = STATE_UNKNOWN
            
            self.uniqueid = self._charger_id + "-" + self._identifier
            _LOGGER.debug("%s - %s: __init__ complete (uid: %s)", self._charger_id, self._identifier, self.uniqueid)
        except Exception as e:            
            _LOGGER.error("%s - %s: __init__ failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


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
        _LOGGER.debug("%s - %s: entity_category: is %s", self._charger_id, self._identifier, self._entity_category)
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
        #TO-BE-DONE: create an option to register some props for being "watched" & "unwatched"
        #   (e.g. charging state etc. while charging), and use push function as message_callback
        #   https://github.com/joscha82/wattpilot/blob/main/shell.py#L100
        return True


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
        """Async: Get latest data and states from the device."""
        try:
            _LOGGER.debug("%s - %s: update", self._charger_id, self._identifier)
            if self._source == 'attribute':
                state = getattr(self._charger,self._identifier,STATE_UNKNOWN)
            elif self._source == 'property':
                state = await async_GetChargerProp(self._charger,self._identifier,STATE_UNKNOWN)
                if str(state).startswith('namespace'):
                    _LOGGER.debug("%s - %s: update: namespace value", self._charger_id, self._identifier)
                    namespace=state
                    if self._entity_cfg.get('value_id', None) is None:
                        _LOGGER.error("%s - %s: update failed: please specific the 'value_id' to use as state value", self._charger_id, self._identifier) 
                        return None
                    state = getattr(namespace,self._entity_cfg.get('value_id',STATE_UNKNOWN),STATE_UNKNOWN)
                    _LOGGER.debug("%s - %s: update: new state: %s", self._charger_id, self._identifier, state)
                    for attr_id in self._entity_cfg.get('attribute_ids', None):
                        _LOGGER.debug("%s - %s: update: adding attribute: %s", self._charger_id, self._identifier, attr_id)
                        self._attributes[attr_id] = getattr(namespace,attr_id,STATE_UNKNOWN)
                elif isinstance(state, list):
                    _LOGGER.debug("%s - %s: update: list value", self._charger_id, self._identifier)
                    state_list=state
                    state=state_list[0]
                    i=1
                    for attr_state in state_list[1:]:
                        self._attributes['state'+str(i)]=attr_state
                        i=i+1
            self._state = state
            self.async_write_ha_state()
            #_LOGGER.debug("%s - %s: update complete: %s", self._charger_id, self._identifier, state)
        except Exception as e:
            _LOGGER.error("%s - %s: update failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
