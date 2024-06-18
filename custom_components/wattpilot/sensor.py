"""Sensor entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import aiofiles
import yaml
import os

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorStateClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
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
)

_LOGGER: Final = logging.getLogger(__name__)
platform='sensor'

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the sensor platform."""
    _LOGGER.debug("Setting up %s platform entry: %s", platform, entry.entry_id)
    entites=[]
    try:
        _LOGGER.debug("%s - async_setup_entry %s: Reading static yaml configuration", entry.entry_id, platform)
        async with aiofiles.open(os.path.dirname(os.path.realpath(__file__))+'/'+platform+'.yaml', 'r') as y: 
            yaml_cfg=yaml.safe_load(await y.read())
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
            if not 'id' in entity_cfg or entity_cfg['id'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id: %s", entry.entry_id, platform, entity_cfg)
                continue
            elif not 'source' in entity_cfg or entity_cfg['source'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no source: %s", entry.entry_id, platform, entity_cfg)
                continue
            entity=ChargerSensor(hass, entry, entity_cfg, charger)
            #entity=ChargerPlatformEntity(hass, entry, entity_cfg, charger)
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


class ChargerSensor(ChargerPlatformEntity):
    """Sensor class for Fronius Wattpilot integration."""

    def _init_platform_specific(self):
        """Platform specific init actions"""
        self._state_enum = self._entity_cfg.get('enum', None)
        self._state_class = self._entity_cfg.get('state_class', None)
        if not self._state_class is None:
            self._state_class = self._state_class.lower()
            _LOGGER.debug("%s - %s: _init_platform_specific: specified state_class is: %s)", self._charger_id, self._identifier, self._state_class)
            if self._state_class == 'measurement':
                self._state_class = SensorStateClass.MEASUREMENT
            elif self._state_class == 'total': 
                self._state_class = SensorStateClass.TOTAL
            elif self._state_class == 'total_increasing': 
                self._state_class = SensorStateClass.TOTAL_INCREASING
            else:
                _LOGGER.warning("%s - %s: _init_platform_specific: invalid state_class defined: %s", self._charger_id, self._identifier, self._state_class)
                self._state_class = None
        if not self._state_enum is None:
           self._state_enum = dict(self._state_enum)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state_class of the entity."""
        _LOGGER.debug("%s - %s: state_class: property requested", self._charger_id, self._identifier)
        return self._state_class

    @property
    def capability_attributes(self):
        if not self.state_class is None:
            return {"state_class": self.state_class}


    async def _async_update_validate_platform_state(self, state=None):
        """Async: Validate the given state for sensor specific requirements"""
        try:
            if self._state_enum is None:
                pass
            elif state is None or state == 'None':
                state = STATE_UNKNOWN
            elif state in list(self._state_enum.keys()):
                state = self._state_enum[state]
            elif state in list(self._state_enum.values()):
                pass
            else:
                _LOGGER.warning("%s - %s: _async_update_validate_platform_state failed: state %s not within enum values: %s", self._charger_id, self._identifier, state, self._state_enum)
            return state
        except Exception as e:
            _LOGGER.error("%s - %s: _async_update_validate_platform_state failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None

