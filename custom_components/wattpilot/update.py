"""Sensor entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import aiofiles
import yaml
import os

from homeassistant.core import (
    callback,
    HomeAssistant,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)

from homeassistant.const import (
    STATE_UNKNOWN,
)

from .entities import ChargerPlatformEntity

from .const import (
    CONF_CHARGER,
    CONF_PUSH_ENTITIES,
    DOMAIN,
)

_LOGGER: Final = logging.getLogger(__name__)
platform='update'

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the update platform."""
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
            entity_cfg['source'] = 'property'
            if not 'id' in entity_cfg or entity_cfg['id'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id: %s", entry.entry_id, platform, entity_cfg)
                continue
            elif not 'source' in entity_cfg or entity_cfg['source'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no source: %s", entry.entry_id, platform, entity_cfg)
                continue
            entity=ChargerUpdate(hass, entry, entity_cfg, charger)
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


class ChargerUpdate(ChargerPlatformEntity, UpdateEntity):
    """Sensor class for Fronius Wattpilot integration."""
    
    def _init_platform_specific(self):
        """Platform specific init actions"""
        _LOGGER.debug("%s - %s: _init_platform_specific", self._charger_id, self._identifier)
        self._attr_installed_version = getattr(self._charger,'firmware',GetChargerProp(self._charger,'onv', None))
        self._attr_supported_features |= UpdateEntityFeature.INSTALL
        self._attr_supported_features |= UpdateEntityFeature.PROGRESS
        self._attr_supported_features |= UpdateEntityFeature.SPECIFIC_VERSION
        _LOGGER.debug("%s - %s: _init_platform_specific complete", self._charger_id, self._identifier)
  
  
    async def async_install(self, version: str | None, backup: bool, **kwargs: Any ) -> None:
        """Install an update.

        Version can be specified to install a specific version. When `None`, the
        latest version needs to be installed.

        The backup parameter indicates a backup should be taken before
        installing the update.
        """
        try:
            _LOGGER.debug("%s - %s: async_install: update charger to: %s", self._charger_id, self._identifier, version)
            await async_SetChargerProp(self._charger,'oct',self._set_value,force=True,force_type=self._set_type)
        except Exception as e:
            _LOGGER.error("%s - %s: async_install failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    @callback
    def async_update_state(self, event: ItemEvent, obj_id: str) -> None:
        """Update entity state.

        Update in_progress, installed_version and latest_version.
        """
        self._attr_in_progress = GetChargerProp(self._charger,'ccu', None)
        self._attr_installed_version = getattr(self._charger,'firmware',GetChargerProp(self._charger,'onv', None))