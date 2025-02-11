"""Sensor entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import aiofiles
import yaml
import os
import html

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    SensorStateClass,
    SensorEntity,
    UNIT_CONVERTERS,
)
from homeassistant.const import STATE_UNKNOWN

from .entities import ChargerPlatformEntity

from .const import (
    CONF_CHARGER,
    CONF_PUSH_ENTITIES,
    DOMAIN,
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
            if getattr(entity,'_init_failed', True): continue
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


class ChargerSensor(ChargerPlatformEntity, SensorEntity):
    """Sensor class for Fronius Wattpilot integration."""
    _state_attr='_attr_native_value'
    
    def _init_platform_specific(self):
        """Platform specific init actions"""
        self._attr_native_unit_of_measurement = self._entity_cfg.get('unit_of_measurement', None)
        if (not (unit_converter := UNIT_CONVERTERS.get(self._attr_device_class)) is None and self._attr_native_unit_of_measurement in unit_converter.VALID_UNITS):
            self._attr_suggested_unit_of_measurement = self._entity_cfg.get('unit_of_measurement', None)
        if not self._entity_cfg.get('state_class', None) is None:
            self._attr_state_class= SensorStateClass((self._entity_cfg.get('state_class')).lower())
        if not self._entity_cfg.get('enum', None) is None:
           self._state_enum = dict(self._entity_cfg.get('enum', None))
        if not self._entity_cfg.get('html_escape', None) is None:
           self._html_escape = True

    async def _async_update_validate_platform_state(self, state=None):
        """Async: Validate the given state for sensor specific requirements"""
        try:
            if state is None or state == 'None':
                state = STATE_UNKNOWN
            elif hasattr(self,'_html_escape') and self._html_escape:
                state = html.unescape(state)
            elif not hasattr(self,'_state_enum'):
                pass
            elif state in list(self._state_enum.keys()):
                state = self._state_enum[state]
            elif state in list(self._state_enum.values()):
                pass
            else:
                _LOGGER.warning("%s - %s: _async_update_validate_platform_state failed: state %s not within enum values: %s", self._charger_id, self._identifier, state, self._state_enum)
            if not self._attr_native_unit_of_measurement is None: self._attr_native_value = state
            return state
        except Exception as e:
            _LOGGER.error("%s - %s: _async_update_validate_platform_state failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None

