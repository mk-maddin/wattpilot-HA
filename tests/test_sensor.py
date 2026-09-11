"""Tests for sensor.py — ChargerSensor and state validation."""

from __future__ import annotations
import asyncio
import unittest.mock as mock
import pytest

from tests.conftest import ChargerSensor, MockCharger

STATE_UNKNOWN = "unknown"


def _make_hass():
    hass = mock.MagicMock()
    hass.data = {"wattpilot": {"test_entry_id": {"params": {"connection": "local"}}}}
    return hass


def _make_entry(name="TestCharger"):
    entry = mock.MagicMock()
    entry.data = {"friendly_name": name, "host": "192.168.1.1", "params": {}}
    entry.entry_id = "test_entry_id"
    return entry


def _sensor(cfg, charger=None):
    if charger is None:
        charger = MockCharger()
    return ChargerSensor(_make_hass(), _make_entry(), cfg, charger)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Sensor init
# ---------------------------------------------------------------------------

class TestSensorInit:

    def test_numeric_sensor_inits_with_unit(self):
        s = _sensor({"id": "eto", "source": "property", "name": "Charged",
                     "device_class": "energy", "state_class": "total",
                     "unit_of_measurement": "Wh", "default_state": -1})
        assert s._init_failed is False
        assert s._attr_native_unit_of_measurement == "Wh"

    def test_enum_sensor_stores_enum_dict(self):
        s = _sensor({"id": "car", "source": "property", "name": "CarState",
                     "enum": {0: "Unknown", 1: "Idle", 2: "Charging"}})
        assert s._init_failed is False
        assert hasattr(s, "_state_enum")
        assert s._state_enum[1] == "Idle"

    def test_sensor_without_unit_has_no_native_unit(self):
        s = _sensor({"id": "car", "source": "property", "name": "CarState"})
        assert s._init_failed is False
        assert s._attr_native_unit_of_measurement is None

    def test_state_class_set_correctly(self):
        s = _sensor({"id": "eto", "source": "property", "name": "Charged",
                     "device_class": "energy", "state_class": "total",
                     "unit_of_measurement": "Wh", "default_state": -1})
        assert s._init_failed is False
        assert hasattr(s, "_attr_state_class")


# ---------------------------------------------------------------------------
# Bug #3 regression — temperature sensor must not store 'unknown' as native_value
# ---------------------------------------------------------------------------

class TestSensorStateValidation:

    async def test_unknown_state_not_written_to_native_value(self):
        """STATE_UNKNOWN must not reach _attr_native_value of a numeric sensor."""
        s = _sensor({"id": "eto", "source": "property", "name": "Charged",
                     "device_class": "energy", "state_class": "total",
                     "unit_of_measurement": "Wh", "default_state": -1})
        if s._init_failed:
            pytest.skip("eto not available")

        # Prime with a valid numeric value
        s._attr_native_value = 9999

        result = await s._async_update_validate_platform_state(STATE_UNKNOWN)

        # None makes async_local_push skip its setattr and async_write_ha_state
        assert result is None
        assert not isinstance(s._attr_native_value, str)

    async def test_valid_numeric_state_updates_native_value(self):
        s = _sensor({"id": "eto", "source": "property", "name": "Charged",
                     "device_class": "energy", "state_class": "total",
                     "unit_of_measurement": "Wh", "default_state": -1})
        if s._init_failed:
            pytest.skip("eto not available")

        result = await s._async_update_validate_platform_state(12345)
        assert result == 12345
        assert s._attr_native_value == 12345

    async def test_none_state_becomes_unknown(self):
        s = _sensor({"id": "car", "source": "property", "name": "CarState"})
        if s._init_failed:
            pytest.skip("car not available")
        result = await s._async_update_validate_platform_state(None)
        assert result == STATE_UNKNOWN

    async def test_none_string_state_becomes_unknown(self):
        s = _sensor({"id": "car", "source": "property", "name": "CarState"})
        if s._init_failed:
            pytest.skip("car not available")
        result = await s._async_update_validate_platform_state("None")
        assert result == STATE_UNKNOWN

    async def test_enum_int_key_mapped_to_string(self):
        s = _sensor({"id": "car", "source": "property", "name": "CarState",
                     "enum": {0: "Unknown", 1: "Idle", 2: "Charging", 3: "Wait Car"}})
        if s._init_failed:
            pytest.skip("car not available")
        result = await s._async_update_validate_platform_state(2)
        assert result == "Charging"

    async def test_enum_passthrough_for_already_string_value(self):
        s = _sensor({"id": "car", "source": "property", "name": "CarState",
                     "enum": {0: "Unknown", 1: "Idle", 2: "Charging"}})
        if s._init_failed:
            pytest.skip("car not available")
        result = await s._async_update_validate_platform_state("Idle")
        assert result == "Idle"

    async def test_sensor_without_unit_does_not_set_native_value(self):
        """Sensors without a unit_of_measurement must not touch _attr_native_value."""
        s = _sensor({"id": "car", "source": "property", "name": "CarState"})
        if s._init_failed:
            pytest.skip("car not available")
        if not hasattr(s, "_attr_native_value"):
            s._attr_native_value = "sentinel"
        sentinel = s._attr_native_value
        await s._async_update_validate_platform_state(42)
        # No unit → assignment skipped → value unchanged
        assert s._attr_native_value == sentinel
