"""Tests for entities.py — ChargerPlatformEntity base class."""

from __future__ import annotations
import asyncio
import unittest.mock as mock
import pytest

from tests.conftest import ChargerPlatformEntity, MockCharger, MockChargerMissingProps

import custom_components.wattpilot.entities as entities_module

STATE_UNKNOWN = "unknown"


def _make_hass():
    hass = mock.MagicMock()
    hass.data = {
        "wattpilot": {
            "test_entry_id": {"params": {"connection": "local"}}
        }
    }
    return hass


def _make_entry(name="TestCharger"):
    entry = mock.MagicMock()
    entry.data = {"friendly_name": name, "host": "192.168.1.1", "params": {}}
    entry.entry_id = "test_entry_id"
    return entry


def _run(coro):
    return asyncio.run(coro)


def _entity(cfg, charger=None):
    hass = _make_hass()
    entry = _make_entry()
    if charger is None:
        charger = MockCharger()
    return ChargerPlatformEntity(hass, entry, cfg, charger)


# ---------------------------------------------------------------------------
# Bug #1 regression — entity_category must never raise AttributeError
# ---------------------------------------------------------------------------

class TestEntityCategoryDefault:

    def test_class_level_default_exists(self):
        """Class-level _entity_category = None must be present so HA can call
        the property even on entities that returned early from __init__."""
        assert hasattr(ChargerPlatformEntity, "_entity_category")
        assert ChargerPlatformEntity._entity_category is None

    def test_entity_category_property_accessible_on_new_instance(self):
        entity = ChargerPlatformEntity.__new__(ChargerPlatformEntity)
        # Must not raise AttributeError
        _ = entity.entity_category

    def test_entity_category_none_when_not_configured(self, charger):
        e = _entity({"id": "car", "source": "property", "name": "CarState"}, charger)
        if not e._init_failed:
            assert e.entity_category is None

    def test_entity_category_set_when_configured(self, charger):
        e = _entity({"id": "car", "source": "property", "name": "CarState",
                     "entity_category": "diagnostic"}, charger)
        if not e._init_failed:
            assert e.entity_category is not None


# ---------------------------------------------------------------------------
# Bug #2 regression — namespacelist subscript on non-list must not crash
# ---------------------------------------------------------------------------

class TestNamespacelistGuard:

    def test_missing_cards_sets_init_failed_without_crashing(self, charger_no_optional):
        """cards_0 with default_state=-1 (int): must set _init_failed, not TypeError."""
        cfg = {
            "id": "cards_0", "source": "namespacelist", "name": "ID Chip 0",
            "namespace_id": 0, "default_state": -1,
            "value_id": "energy", "attribute_ids": ["name", "cardId"],
        }
        e = ChargerPlatformEntity(_make_hass(), _make_entry(), cfg, charger_no_optional)
        assert e._init_failed is True

    def test_cards_present_succeeds(self, charger):
        cfg = {
            "id": "cards_0", "source": "namespacelist", "name": "ID Chip 0",
            "namespace_id": 0, "default_state": -1,
            "value_id": "energy", "attribute_ids": ["name", "cardId"],
        }
        e = ChargerPlatformEntity(_make_hass(), _make_entry(), cfg, charger)
        assert e._init_failed is False

    def test_available_returns_false_not_crashes(self, charger_no_optional):
        """available property must not TypeError when cards is absent."""
        cfg = {
            "id": "cards_0", "source": "namespacelist", "name": "ID Chip 0",
            "namespace_id": 0, "default_state": -1,
            "value_id": "energy", "attribute_ids": ["name", "cardId"],
        }
        e = ChargerPlatformEntity(_make_hass(), _make_entry(), cfg, charger_no_optional)
        assert e.available is False  # must not raise


# ---------------------------------------------------------------------------
# General init / available
# ---------------------------------------------------------------------------

class TestEntityInitBasic:

    def test_property_entity_inits(self, charger):
        e = _entity({"id": "car", "source": "property", "name": "CarState"}, charger)
        assert e._init_failed is False

    def test_attribute_entity_inits(self, charger):
        e = _entity({"id": "AccessState", "source": "attribute", "name": "AccessState"}, charger)
        assert e._init_failed is False

    def test_unknown_property_sets_init_failed(self, charger):
        e = _entity({"id": "does_not_exist", "source": "property", "name": "X"}, charger)
        assert e._init_failed is True

    def test_unique_id_contains_charger_name(self, charger):
        entry = _make_entry("GarageWP")
        e = ChargerPlatformEntity(_make_hass(), entry,
                                  {"id": "car", "source": "property", "name": "Car"}, charger)
        if not e._init_failed:
            assert "GarageWP" in e._attr_unique_id

    def test_attr_name_contains_charger_name(self, charger):
        entry = _make_entry("GarageWP")
        e = ChargerPlatformEntity(_make_hass(), entry,
                                  {"id": "car", "source": "property", "name": "CarState"}, charger)
        if not e._init_failed:
            assert "GarageWP" in e._attr_name

    def test_available_true_for_healthy(self, charger):
        e = _entity({"id": "car", "source": "property", "name": "Car"}, charger)
        if not e._init_failed:
            assert e.available is True

    def test_available_false_when_disconnected(self):
        c = MockCharger()
        c.connected = False
        e = _entity({"id": "car", "source": "property", "name": "Car"}, c)
        if not e._init_failed:
            assert e.available is False

    def test_available_false_when_not_initialized(self):
        c = MockCharger()
        c.allPropsInitialized = False
        e = _entity({"id": "car", "source": "property", "name": "Car"}, c)
        if not e._init_failed:
            assert e.available is False


class TestMissingOptionalProperties:
    """upo/cus/ffb/lck not present on all chargers — must fail gracefully."""

    @pytest.mark.parametrize("prop_id", ["upo", "cus", "ffb", "lck"])
    def test_missing_prop_sets_init_failed(self, charger_no_optional, prop_id):
        e = _entity({"id": prop_id, "source": "property", "name": prop_id.upper()},
                    charger_no_optional)
        assert e._init_failed is True


# ---------------------------------------------------------------------------
# Issue #144 regression — push/poll must not run on entities that have no hass
# ---------------------------------------------------------------------------

class TestPushGuardForNeverAddedEntity:
    """An entity disabled via ``enabled: False`` is aborted by Home Assistant
    with ``add_to_platform_abort()``, which leaves ``hass`` as None and never
    assigns ``registry_entry``. ``Entity.enabled`` returns True whenever
    ``registry_entry`` is None, so the enabled check alone lets the push
    through and ``async_write_ha_state()`` then raises every time the charger
    pushes a value."""

    CFG = {"id": "rbt", "source": "property", "name": "Reboot Timer"}

    def test_push_does_not_write_state_when_hass_is_none(self, charger):
        e = _entity(self.CFG, charger)
        e.hass = None
        e.async_write_ha_state = mock.MagicMock()
        assert e.enabled is True
        _run(e.async_local_push(1234))
        e.async_write_ha_state.assert_not_called()

    def test_poll_does_not_write_state_when_hass_is_none(self, charger):
        e = _entity(self.CFG, charger)
        e.hass = None
        e.async_write_ha_state = mock.MagicMock()
        _run(e.async_local_poll())
        e.async_write_ha_state.assert_not_called()

    def test_push_does_not_log_an_error_when_hass_is_none(self, charger):
        """Real Home Assistant raises RuntimeError("Attribute hass is None")
        from async_write_ha_state() when hass is None, which the integration
        then logs once per pushed value."""
        e = _entity(self.CFG, charger)
        e.hass = None
        e.async_write_ha_state = mock.MagicMock(
            side_effect=RuntimeError("Attribute hass is None for <entity unknown.unknown=unknown>")
        )
        with mock.patch.object(entities_module._LOGGER, "error") as err:
            _run(e.async_local_push(1234))
        err.assert_not_called()

    def test_push_still_writes_state_for_an_added_entity(self, charger):
        """Guard must not suppress updates for normally added entities."""
        e = _entity({"id": "car", "source": "property", "name": "Car"}, charger)
        if e._init_failed:
            pytest.skip("entity did not initialise")
        e.async_write_ha_state = mock.MagicMock()
        assert e.hass is not None
        _run(e.async_local_push(2))
        e.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# Recorder load — attribute-only updates are throttled
# ---------------------------------------------------------------------------

class TestAttributeOnlyWriteThrottle:
    """Charging Power pushes new per-phase voltages ~1/s while idle at 0 W.
    Each write bumps last_updated and costs a recorder row, so writes where
    only attributes changed are limited to one per interval."""

    CFG = {"id": "car", "source": "property", "name": "CarState"}

    def _counting_entity(self, charger):
        e = _entity(self.CFG, charger)
        e.async_write_ha_state = mock.MagicMock()
        return e

    def test_unchanged_state_written_once_per_interval(self, charger):
        e = self._counting_entity(charger)
        with mock.patch.object(entities_module, "time") as clock:
            clock.monotonic.side_effect = [0, 1, 2, 61]
            for _ in range(4):
                _run(e.async_local_push(0))
        assert e.async_write_ha_state.call_count == 2

    def test_changed_state_always_written(self, charger):
        e = self._counting_entity(charger)
        with mock.patch.object(entities_module, "time") as clock:
            clock.monotonic.side_effect = [0, 1, 2]
            for value in (0, 1, 2):
                _run(e.async_local_push(value))
        assert e.async_write_ha_state.call_count == 3
