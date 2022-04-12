"""Switch entities for the Fronius Wattpilot integration."""

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
from homeassistant.const import (
    CONF_FRIENDLY_NAME,
    CONF_IP_ADDRESS,
    STATE_ON,
    STATE_OFF,
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
platform='switch'

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the switch platform."""
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
            entity=ChargerSwitch(hass, entry, entity_cfg, charger)
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


class ChargerSwitch(ChargerPlatformEntity):
    """Switch class for Fronius Wattpilot integration."""


    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, entity_cfg, charger) -> None:
        """Initialize the object."""
        try:
            self.hass = hass
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

            self._set_identifier = self._entity_cfg.get('set_id', None) 
            if self._set_identifier == self._identifier:
                self._set_identifier = None

            self._name = self._charger_id + ' ' + self._entity_cfg.get('name', self._entity_cfg.get('id'))
            self._icon = self._entity_cfg.get('icon', None)
            self._device_class = self._entity_cfg.get('device_class', None)
            self._unit_of_measurement = self._entity_cfg.get('unit_of_measurement', None)
            self._entity_category = self._entity_cfg.get('entity_category', None)

            self._attributes = {}
            self._attributes['description'] = self._entity_cfg.get('description', None)
            self._state = STATE_UNKNOWN

            self.uniqueid = self._charger_id + "-" + self._identifier
            #_LOGGER.debug("%s - %s: __init__ complete (uid: %s)", self._charger_id, self._identifier, self.uniqueid)
        except Exception as e:
            _LOGGER.error("%s - %s: __init__ failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    async def _async_update_validate_platform_state(self, state=None):
        """Async: Validate the given state for switch specific requirements"""
        try:
            if str(state) in [ STATE_ON, STATE_OFF, STATE_UNKNOWN ]:
                pass
            elif str(state).lower() == 'true':
                state = STATE_ON
            elif str(state).lower() == 'false':
                state = STATE_OFF
            else:
                _LOGGER.warning("%s - %s: _async_update_validate_platform_state failed: state %s not valid for switch platform", self._charger_id, self._identifier, state)
                state = STATE_UNKNOWN
            return state
        except Exception as e:
            _LOGGER.error("%s - %s: _async_update_validate_platform_state failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None


    @property
    def is_on(self) -> bool:
        """Return true if entity is on."""
        if self._entity_cfg.get('invert', False):
            if self._state == STATE_ON : 
                return False
            return True
        elif self._state == STATE_ON: 
           return True
        return False


    async def async_turn_on(self, **kwargs) -> None:
        """Async: Turn entity on"""
        try:
            _LOGGER.debug("%s - %s: async_turn_on: %s", self._charger_id, self._identifier, self._name)
            if self._entity_cfg.get('invert', False):
                value = False
            else:
                value = True
            if not self._set_identifier is None:
                await async_SetChargerProp(self._charger,self._set_identifier,value,True)
            else:
                await async_SetChargerProp(self._charger,self._identifier,value)
        except Exception as e:
            _LOGGER.error("%s - %s: async_turn_on failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    async def async_turn_off(self, **kwargs) -> None:
        """Async: Turn entity off"""
        try:
            _LOGGER.debug("%s - %s: async_turn_off: %s", self._charger_id, self._identifier, self._name)
            if self._entity_cfg.get('invert', False):
                value = True
            else:
                value = False
            if not self._set_identifier is None:
                await async_SetChargerProp(self._charger,self._set_identifier,value,True)
            else:
                await async_SetChargerProp(self._charger,self._identifier,value)        
        except Exception as e:
            _LOGGER.error("%s - %s: async_turn_off failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
