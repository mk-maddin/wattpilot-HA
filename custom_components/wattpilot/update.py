"""Sensor entities for the Fronius Wattpilot integration."""

from __future__ import annotations
from typing import Final
import logging
import asyncio
import aiofiles
import yaml
import os
import re
from packaging.version import Version

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

from .utils import (
    async_ProgrammingDebug,
    async_SetChargerProp,
    GetChargerProp,
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
            elif not 'id_installed' in entity_cfg or entity_cfg['id_installed'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id_installed: %s", entry.entry_id, platform, entity_cfg)
                continue
            elif not 'id_trigger' in entity_cfg or entity_cfg['id_trigger'] is None:
                _LOGGER.error("%s - async_setup_entry %s: Invalid yaml configuration - no id_trigger: %s", entry.entry_id, platform, entity_cfg)
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
    """Update class for Fronius Wattpilot integration."""
    _state_attr='_attr_latest_version'
    _dummy_version = '0.0.1'
    _available_versions = {}
    
    def _init_platform_specific(self):
        """Platform specific init actions"""
        _LOGGER.debug("%s - %s: _init_platform_specific", self._charger_id, self._identifier)
        self._identifier_installed = self._entity_cfg.get('id_installed')
        self._identifier_trigger = self._entity_cfg.get('id_trigger', None)
        self._identifier_status = self._entity_cfg.get('id_status', None)
        
        self._attr_installed_version = GetChargerProp(self._charger,self._identifier_installed, None)
        self._attr_latest_version = self._update_available_versions(None,True)
        
        if not self._identifier_trigger is None:
            self._attr_supported_features |= UpdateEntityFeature.INSTALL
            self._attr_supported_features |= UpdateEntityFeature.SPECIFIC_VERSION
        if not self._identifier_status is None:
            self._attr_supported_features |= UpdateEntityFeature.PROGRESS            
        _LOGGER.debug("%s - %s: _init_platform_specific complete", self._charger_id, self._identifier)


    def _update_available_versions(self, v_list=None, return_latest=False):
        """Get the latest update version of available versions"""
        _LOGGER.debug("%s - %s: _update_available_versions", self._charger_id, self._identifier)
        try:
            if v_list is None: v_list = GetChargerProp(self._charger,self._identifier, None)
            if v_list is None and hasattr(self, _attr_installed_version) and not self._attr_installed_version is None:
                v_list = [ self._attr_installed_version ]
            elif v_list is None: v_list = [ self._dummy_version ]
            elif not isinstance(v_list, list): v_list = [ v_list ]
            self._available_versions = self._get_versions_dict(v_list)          
            latest = list(self._available_versions.keys())
            latest.sort(key=Version)               
            return latest[-1]
        except Exception as e:
            _LOGGER.error("%s - %s: _get_versions_dict failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            if return_latest: self._dummy_version
            return None


    def _get_versions_dict(self, v_list:list ) -> dict|None:
        """Create a dict with clean and named versions"""
        _LOGGER.debug("%s - %s: _get_versions_dict", self._charger_id, self._identifier)
        try:
            versions = {}
            for v in v_list:
                c = (v.lower()).replace('x','0')
                c = re.sub(r'^(v|ver|vers|version)*\s*\.*\s*([0-9.x]*)\s*-?\s*((alpha|beta|dev|rc|post|a|b|release)+[0-9]*)?\s*.*$',r'\2\3',c)
                versions[c]=v
            return versions
        except Exception as e:
            _LOGGER.error("%s - %s: _get_versions_dict failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)
            return None
 
 
    async def async_install(self, version: str | None, backup: bool, **kwargs: Any ) -> None:
        """Trigger update install"""
        try:
            _LOGGER.debug("%s - %s: async_install: update charger to: %s", self._charger_id, self._identifier, version)
            if version is None: version = self._attr_latest_version
            v_name = getattr(self._available_versions, version, None)
            if v_name is none:
                _LOGGER.error("%s - %s: async_install failed: incorrect version: %s", self._charger_id, self._identifier, version)
                return
            _LOGGER.debug("%s - %s: async_install: trigger charger update via: %s -> %s", self._charger_id, self._identifier, self._identifier_trigger, v_name)
            #await async_SetChargerProp(self._charger,self._identifier_trigger,v_name,force=False,force_type=self._set_type)
            #self._attr_in_progress = true
        except Exception as e:
            _LOGGER.error("%s - %s: async_install failed: %s (%s.%s)", self._charger_id, self._identifier, str(e), e.__class__.__module__, type(e).__name__)


    async def _async_update_validate_platform_state(self, state=None):
        """Async: Validate the given state for sensor specific requirements"""
        _LOGGER.debug("%s - %s: _async_update_validate_platform_state", self._charger_id, self._identifier)
        state = await self._hass.async_add_executor_job(self._update_available_versions, state, True)
        _LOGGER.debug("%s - %s: _async_update_validate_platform_state: state: %s", self._charger_id, self._identifier, state)
        return state

    @callback
    def async_update_state(self, event: ItemEvent, obj_id: str) -> None:
        """Update entity state.

        Update in_progress, installed_version and latest_version.
        """
        _LOGGER.debug("%s - %s: async_update_state", self._charger_id, self._identifier)
        _LOGGER.debug("%s - %s: async_update_state: event: %s", self._charger_id, self._identifier, event)
        _LOGGER.debug("%s - %s: async_update_state: obj_id: %s", self._charger_id, self._identifier, obj_id)
#        self._attr_installed_version = getattr(self._charger,'firmware',GetChargerProp(self._charger,'onv', None))