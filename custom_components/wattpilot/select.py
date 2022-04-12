"""Sensor entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import yaml
import os

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.select import SelectEntity
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_IP_ADDRESS,
    STATE_UNKNOWN,
)

from .entities import ChargerPlatformEntity

from .const import (
    CONF_CHARGER,
    DEFAULT_NAME,
    DOMAIN,
)
from .utils import (
    async_ProgrammingDebug,
    async_GetChargerProp,
    GetChargerProp,
    async_SetChargerProp,
)

_LOGGER: Final = logging.getLogger(__name__)
platform='select'

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the sensor platform."""
    _LOGGER.debug("Setting up %s platform entry: %s", platform, entry.entry_id)
    entites=[]
    try:
        _LOGGER.debug("%s - async_setup_entry %s: Reading static yaml configuration", entry.entry_id, platform)
        with open(os.path.dirname(os.path.realpath(__file__))+'/'+platform+'.yaml', 'r') as stream:
            yaml_cfg=yaml.safe_load(stream)
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry %s: Reading static yaml configuration failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return False

    try:
        _LOGGER.debug("%s - async_setup_entry %s: Getting charger instance from data store", entry.entry_id, platform)
        charger=hass.data[DOMAIN][entry.entry_id][CONF_CHARGER]
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry %s: Getting charger instance from data store failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
        return False

    for entity_cfg in yaml_cfg[platform]:
        try:
            entity_cfg['source'] = 'property'
            if not 'id' in entity_cfg or entity_cfg['id'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id: %s", entry.entry_id, platform, entity_cfg)
                continue
            elif not 'source' in entity_cfg or entity_cfg['source'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no source: %s", entry.entry_id, platform, entity_cfg)
                continue            
            entity=ChargerSelect(entry, entity_cfg, charger)
            entites.append(entity)
            await asyncio.sleep(0)
        except Exception as e:
            _LOGGER.error("%s - async_setup_entry %s: Reading static yaml configuration failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
            return False

    _LOGGER.info("%s - async_setup_entry: setup %s %s entities", entry.entry_id, len(entites), platform)
    if not entites:
        return None
    async_add_entities(entites)


class ChargerSelect(ChargerPlatformEntity, SelectEntity):
    """Select class for Fronius Wattpilot integration."""


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

            self._opt_identifier = self._entity_cfg.get('options_id', None)
            _LOGGER.debug("%s - %s: __init__ opt_identifier: %s)", self._charger_id, self._identifier, self._opt_identifier)
            self._opt_dict = getattr(self._charger,self._opt_identifier,list(STATE_UNKNOWN))
            _LOGGER.debug("%s - %s: __init__ opt_enum: %s)", self._charger_id, self._identifier, self._opt_dict) 
            if not self._opt_dict == STATE_UNKNOWN:
                self._attr_options = list(self._opt_dict.values())
            _LOGGER.debug("%s - %s: __init__ attr_options: %s)", self._charger_id, self._identifier, self._attr_options) 

            self._attributes = {}
            self._attributes['description'] = self._entity_cfg.get('description', None)
            self._state = STATE_UNKNOWN
 
            self.uniqueid = self._charger_id + "-" + self._identifier
            _LOGGER.debug("%s - %s: __init__ complete (uid: %s)", self._charger_id, self._identifier, self.uniqueid)
        except Exception as e:            
            _LOGGER.error("%s - %s: __init__ failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    async def async_update(self) -> None:
        """Async: Get latest data and states from the device."""
        try:
            #_LOGGER.debug("%s - %s: update", self._charger_id, self._identifier)
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
                    #_LOGGER.debug("%s - %s: update: new state: %s", self._charger_id, self._identifier, state)
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

            _LOGGER.debug("%s - %s: update: validate/match state to select options: %s", self._charger_id, self._identifier, state)
            if state in list(self._opt_dict.keys()):
                state = self._opt_dict[state]
            elif state in list(self._opt_dict.values()):
                pass 
                #state = self._opt_dict(state)
            else:
                _LOGGER.error("%s - %s: update: state %s not within options_id values: %s", self._charger_id, self._identifier, state, self._opt_dict)
                state = STATE_UNKNOWN
            self._state = state
            self.async_write_ha_state()
            #_LOGGER.debug("%s - %s: update complete: %s", self._charger_id, self._identifier, state)
        except Exception as e:
            _LOGGER.error("%s - %s: update failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    async def async_select_option(self, option: str) -> None:
        """Async: Change the selected option."""
        try:
            #_LOGGER.debug("%s - %s: async_select_option: value was changed to: %s", self._charger_id, self._identifier, option)
            key = list(self._opt_dict.keys())[list(self._opt_dict.values()).index(option)] 
            if key is None:
                _LOGGER.error("%s - %s: async_select_option: option %s not within options_id keys: %s", self._charger_id, self._identifier, state, self._opt_dict)
                return None
            _LOGGER.debug("%s - %s: async_select_option: save option key %s", self._charger_id, self._identifier, key)
            await async_SetChargerProp(self._charger,self._identifier,key)
        except Exception as e:
            _LOGGER.error("%s - %s: async_select_option failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)

