"""Button entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import aiofiles
import yaml
import os

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.button import ButtonEntity
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
platform='button'

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

    for entity_cfg in yaml_cfg.get(platform, []):
        try:
            entity_cfg['source'] = 'none'
            if not 'id' in entity_cfg or entity_cfg['id'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id: %s", entry.entry_id, platform, entity_cfg)
                continue
            elif not 'source' in entity_cfg or entity_cfg['source'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no source: %s", entry.entry_id, platform, entity_cfg)
                continue
            entity=ChargerButton(hass, entry, entity_cfg, charger)
            if entity is None: continue
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


class ChargerButton(ChargerPlatformEntity, ButtonEntity):
    """Button class for Fronius Wattpilot integration."""


    def _init_platform_specific(self):
        """Platform specific init actions"""
        self._set_value = self._entity_cfg.get('set_value', None)
        if self._set_value == None:
            _LOGGER.error("%s - %s: __init__: Required configuration option 'set_value' missing - please specify: %s", self._charger_id, self._identifier, self._set_value)
            return None


    async def async_local_poll(self) -> None:
        """Async: Poll the latest data and states from the entity."""
        #no state required for ButtonEntity
        pass


    async def async_press(self) -> None:
        """Async: Handle button press"""
        try:
            await async_SetChargerProp(self._charger,self._identifier,self._set_value,force=True,force_type=self._set_type)
        except Exception as e:
            _LOGGER.error("%s - %s: update failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
