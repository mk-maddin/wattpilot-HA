"""Tests for utils.py — GetChargerProp helper."""

from __future__ import annotations
import types
import pytest

# All imports come from conftest bootstrap
from tests.conftest import GetChargerProp, MockCharger, MockChargerMissingProps


class TestGetChargerProp:

    def test_returns_value_for_known_property(self, charger):
        assert GetChargerProp(charger, "car") == 1

    def test_returns_default_for_missing_property(self, charger):
        assert GetChargerProp(charger, "upo", "MISSING") == "MISSING"

    def test_returns_none_for_missing_property_no_default(self, charger):
        assert GetChargerProp(charger, "does_not_exist") is None

    def test_returns_default_when_property_value_is_none(self):
        c = MockCharger(extra_props={"nullprop": None})
        assert GetChargerProp(c, "nullprop", 42) == 42

    def test_returns_none_when_property_is_none_and_no_default(self):
        c = MockCharger(extra_props={"nullprop": None})
        assert GetChargerProp(c, "nullprop") is None

    def test_missing_cards_returns_int_default_not_raises(self, charger_no_optional):
        """Bug #2 regression: missing cards returns -1 (int), not a crash."""
        result = GetChargerProp(charger_no_optional, "cards", -1)
        assert result == -1
        assert not isinstance(result, list)

    def test_charger_without_allProps_returns_default(self):
        class Bare: pass
        assert GetChargerProp(Bare(), "car", "fallback") == "fallback"

    def test_identifier_none_returns_default(self, charger):
        assert GetChargerProp(charger, None, "X") == "X"

    def test_list_property_returned_intact(self, charger):
        nrg = GetChargerProp(charger, "nrg")
        assert isinstance(nrg, list) and len(nrg) == 16

    def test_namespace_property_returned_intact(self, charger):
        ccw = GetChargerProp(charger, "ccw")
        assert hasattr(ccw, "ssid") and ccw.ssid == "MyWifi"

    def test_known_string_property(self, charger):
        assert GetChargerProp(charger, "sse") == "TEST12345"

    def test_known_int_property(self, charger):
        assert GetChargerProp(charger, "rbc") == 3


class TestPropertyUpdateHandler:

    @staticmethod
    def _utils():
        import sys
        return sys.modules["custom_components.wattpilot.utils"]

    @staticmethod
    def _hass(stopping=False, closed=False):
        from unittest import mock
        hass = mock.MagicMock()
        hass.is_stopping = stopping
        hass.loop.is_closed.return_value = closed
        hass.data = {"wattpilot": {"entry": {}}}
        return hass

    def test_returns_early_when_hass_is_stopping(self):
        from unittest import mock
        utils = self._utils()
        with mock.patch.object(utils.asyncio, "run_coroutine_threadsafe") as run:
            assert utils.PropertyUpdateHandler(self._hass(stopping=True), "entry", "car", 1) is None
        run.assert_not_called()

    def test_returns_early_when_loop_is_closed(self):
        from unittest import mock
        utils = self._utils()
        with mock.patch.object(utils.asyncio, "run_coroutine_threadsafe") as run:
            assert utils.PropertyUpdateHandler(self._hass(closed=True), "entry", "car", 1) is None
        run.assert_not_called()

    def test_scheduling_error_returns_none_not_nameerror(self):
        from unittest import mock
        utils = self._utils()
        with mock.patch.object(utils.asyncio, "run_coroutine_threadsafe", side_effect=RuntimeError("Event loop is closed")):
            handler = mock.MagicMock()
            with mock.patch.object(utils, "async_PropertyUpdateHandler", handler):
                assert utils.PropertyUpdateHandler(self._hass(), "entry", "car", 1) is None
            handler.return_value.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_handler_error_returns_none_not_nameerror(self):
        utils = self._utils()
        hass = self._hass()
        hass.data = {"wattpilot": {}}
        assert await utils.async_PropertyUpdateHandler(hass, "missing_entry", "car", 1) is None


class TestConnectChargerCleanup:

    class _FakeCharger:
        def __init__(self, **kwargs):
            self.name = "fake"
            self.connected = False
            self.allPropsInitialized = False
            self.connect_calls = 0
            self.disconnect_calls = 0

        def connect(self):
            self.connect_calls += 1

        def disconnect(self):
            self.disconnect_calls += 1

    @pytest.mark.asyncio
    async def test_new_charger_disconnected_on_timeout(self):
        import sys
        from unittest import mock
        utils = sys.modules["custom_components.wattpilot.utils"]
        created = []

        def factory(**kwargs):
            created.append(self._FakeCharger())
            return created[-1]

        with mock.patch.object(utils.wattpilot, "Wattpilot", factory, create=True):
            result = await utils.async_ConnectCharger("entry", {"host": "192.0.2.1", "timeout": 0})
        assert result is False
        assert created[0].connect_calls == 1
        assert created[0].disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_existing_charger_kept_on_failed_reconnect(self):
        import sys
        utils = sys.modules["custom_components.wattpilot.utils"]
        existing = self._FakeCharger()
        result = await utils.async_ConnectCharger("entry", {"timeout": 0}, existing)
        assert result is False
        assert existing.disconnect_calls == 0


class TestConnectChargerMissingConfig:

    @pytest.mark.asyncio
    async def test_missing_ip_returns_false_without_creating_charger(self):
        import sys
        from unittest import mock
        utils = sys.modules["custom_components.wattpilot.utils"]
        factory = mock.MagicMock()
        with mock.patch.object(utils.wattpilot, "Wattpilot", factory, create=True):
            assert await utils.async_ConnectCharger("entry", {"connection": "local"}) is False
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_serial_returns_false_without_creating_charger(self):
        import sys
        from unittest import mock
        utils = sys.modules["custom_components.wattpilot.utils"]
        factory = mock.MagicMock()
        with mock.patch.object(utils.wattpilot, "Wattpilot", factory, create=True):
            assert await utils.async_ConnectCharger("entry", {"connection": "cloud"}) is False
        factory.assert_not_called()


class TestSelectEmptyState:

    @staticmethod
    def _select(entity_cfg):
        import sys
        from unittest import mock
        from tests.conftest import _load_file_as_module
        sys.modules.setdefault("homeassistant.components", mock.MagicMock())
        if "homeassistant.components.select" not in sys.modules:
            select_stub = types.ModuleType("homeassistant.components.select")
            select_stub.SelectEntity = type("SelectEntity", (), {})
            sys.modules["homeassistant.components.select"] = select_stub
        mod = _load_file_as_module("custom_components/wattpilot/select.py", "custom_components.wattpilot.select")
        entity = object.__new__(mod.ChargerSelect)
        entity._charger_id = "charger"
        entity._identifier = "ct"
        entity._entity_cfg = entity_cfg
        entity._opt_dict = {"default": "Standard", "kiaSoul": "Kia Soul"}
        return entity

    @pytest.mark.asyncio
    async def test_empty_string_maps_to_configured_empty_state(self):
        entity = self._select({"empty_state": "default"})
        assert await entity._async_update_validate_platform_state("") == "Standard"

    @pytest.mark.asyncio
    async def test_empty_string_without_empty_state_is_unknown(self):
        entity = self._select({})
        assert await entity._async_update_validate_platform_state("") == "unknown"

    @pytest.mark.asyncio
    async def test_empty_state_not_in_options_is_unknown(self):
        entity = self._select({"empty_state": "doesNotExist"})
        assert await entity._async_update_validate_platform_state("") == "unknown"

    @pytest.mark.asyncio
    async def test_known_key_still_mapped(self):
        entity = self._select({"empty_state": "default"})
        assert await entity._async_update_validate_platform_state("kiaSoul") == "Kia Soul"
