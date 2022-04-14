"""Select entities for the Fronius Wattpilot integration."""

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
    CONF_PUSH_ENTITIES,
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

    try:
        _LOGGER.debug("%s - async_setup_entry %s: Getting push entities dict from data store", entry.entry_id, platform)
        push_entities=hass.data[DOMAIN][entry.entry_id][CONF_PUSH_ENTITIES]
    except Exception as e:
        _LOGGER.error("%s - async_setup_entry %s: Getting push entities dict from data store failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
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
            entity=ChargerSelect(hass, entry, entity_cfg, charger)
            entites.append(entity)
            if entity._source == 'property':
                push_entities[entity._identifier]=entity
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


    def _init_platform_specific(self):
        """Platform specific init actions"""
        self._opt_identifier = self._entity_cfg.get('options_id', None)
        #_LOGGER.debug("%s - %s: __init__ opt_identifier: %s)", self._charger_id, self._identifier, self._opt_identifier)
        self._opt_dict = getattr(self._charger,self._opt_identifier,list(STATE_UNKNOWN))
        #_LOGGER.debug("%s - %s: __init__ opt_enum: %s)", self._charger_id, self._identifier, self._opt_dict) 
        if not self._opt_dict == STATE_UNKNOWN:
            self._attr_options = list(self._opt_dict.values())
        #_LOGGER.debug("%s - %s: __init__ attr_options: %s)", self._charger_id, self._identifier, self._attr_options)


    async def _async_update_validate_platform_state(self, state=None):
        """Async: Validate the given state for select specific requirements"""
        try:
            if state in list(self._opt_dict.keys()):
                state = self._opt_dict[state]
            elif state in list(self._opt_dict.values()):
                pass 
            else:
                _LOGGER.error("%s - %s: _async_update_validate_platform_state failed: state %s not within options_id values: %s", self._charger_id, self._identifier, state, self._opt_dict)
                state = STATE_UNKNOWN
            return state
        except Exception as e:
            _LOGGER.error("%s - %s: _async_update_validate_platform_state failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    async def async_select_option(self, option: str) -> None:
        """Async: Change the selected option."""
        try:
            #_LOGGER.debug("%s - %s: async_select_option: value was changed to: %s", self._charger_id, self._identifier, option)
            key = list(self._opt_dict.keys())[list(self._opt_dict.values()).index(option)] 
            if key is None:
                _LOGGER.error("%s - %s: async_select_option: option %s not within options_id keys: %s", self._charger_id, self._identifier, state, self._opt_dict)
                return None
            _LOGGER.debug("%s - %s: async_select_option: save option key %s", self._charger_id, self._identifier, key)
            await async_SetChargerProp(self._charger,self._identifier,key,force_type=self._set_type)
        except Exception as e:
            _LOGGER.error("%s - %s: async_select_option failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)

