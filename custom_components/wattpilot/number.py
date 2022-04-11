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
from homeassistant.components.number import NumberEntity
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
platform='number'

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

    for entity_cfg in yaml_cfg.get(platform, []):
        try:
            entity_cfg['source'] = 'property'
            if not 'id' in entity_cfg or entity_cfg['id'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id: %s", entry.entry_id, platform, entity_cfg)
                continue
            elif not 'source' in entity_cfg or entity_cfg['source'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no source: %s", entry.entry_id, platform, entity_cfg)
                continue
            entity=ChargerNumber(entry, entity_cfg, charger)
            entites.append(entity)
            await asyncio.sleep(0)
        except Exception as e:
            _LOGGER.error("%s - async_setup_entry %s: Reading static yaml configuration failed: %s (%s.%s)", entry.entry_id, platform, str(e), e.__class__.__module__, type(e).__name__)
            return False

    _LOGGER.info("%s - async_setup_entry: setup %s %s entities", entry.entry_id, len(entites), platform)
    if not entites:
        return None
    async_add_entities(entites)


class ChargerNumber(ChargerPlatformEntity, NumberEntity):
    """Sensor class for Fronius Wattpilot integration."""

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

            self._set_type = self._entity_cfg.get('set_type', 'float')
            self._min = float(self._entity_cfg.get('min_value', None))
            self._max = float(self._entity_cfg.get('max_value', None))
            self._step = float(self._entity_cfg.get('step', None))
            self._mode = self._entity_cfg.get('mode', None)

            self._attributes = {}
            self._attributes['description'] = self._entity_cfg.get('description', None)
            self._state = STATE_UNKNOWN
 
            self.uniqueid = self._charger_id + "-" + self._identifier
            _LOGGER.debug("%s - %s: __init__ complete (uid: %s)", self._charger_id, self._identifier, self.uniqueid)
        except Exception as e:            
            _LOGGER.error("%s - %s: __init__ failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None

    @property
    def min_value(self) -> float | None:
        """Return the minimum accepted value (inclusive) for this entity."""
        return self._min

    @property
    def max_value(self) -> float | None:
        """Return the maximum accepted value (inclusive) for this entity."""
        return self._max

    @property
    def step(self) -> float | None:
        """Return the resolution of the values for this entity."""
        return self._step

    @property
    def mode(self) -> str | None:
        """Return the how the number should be displayed  for this entity."""
        return self._mode

    async def async_set_value(self, value: float) -> None:
        """Async: Change the current value."""
        try:
            _LOGGER.debug("%s - %s: async_set_value: value was changed to: %s", self._charger_id, self._identifier, float)
            if (self._identifier == 'fte'):
                _LOGGER.debug("%s - %s: async_set_value: apply ugly workaround to always set next trip distance to kWH instead of KM", self._charger_id, self._identifier)
                await async_SetChargerProp(self._charger,'esk',True)                 
            await async_SetChargerProp(self._charger,self._identifier,value)
        except Exception as e:
            _LOGGER.error("%s - %s: update failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
