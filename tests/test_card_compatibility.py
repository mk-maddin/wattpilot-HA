from __future__ import annotations
import asyncio
import json
import pathlib
import sys
from types import SimpleNamespace
from unittest import mock
import pytest
import yaml
from tests.test_wattpilot_lib import lib, wp
from tests.conftest import ChargerSensor, _load_file_as_module


def _receive(wp, status, message_type="deltaStatus", **extra):
    wp._Wattpilot__on_message(None, json.dumps({"type": message_type, "status": status, **extra}))


@pytest.mark.parametrize("index", range(10))
def test_flat_card_preserves_index_and_falsy_values(wp, index):
    _receive(wp, {f"c{index}n": "Test card", f"c{index}e": 0, f"c{index}i": False, f"c{index}p": "{}"})
    props = wp.allProps
    assert len(props["cards"]) == 10
    assert vars(props["cards"][index]) == {"name": "Test card", "energy": 0, "cardId": False}
    assert all(card is None for i, card in enumerate(props["cards"]) if i != index)
    assert props[f"c{index}p"] == "{}"
    assert "cards" not in wp._allProps


def test_partial_full_status_and_delta_updates(wp):
    _receive(wp, {"c0n": "Test card"}, "fullStatus", partial=True)
    assert wp.allProps["cards"][0] is None
    _receive(wp, {"c0e": 12, "c0i": True}, "fullStatus", partial=False)
    assert wp.allPropsInitialized is True
    assert wp.allProps["cards"][0].energy == 12
    _receive(wp, {"c0e": 13, "c0n": "Renamed card", "c0i": False})
    assert vars(wp.allProps["cards"][0]) == {"name": "Renamed card", "energy": 13, "cardId": False}
    _receive(wp, {"c0e": 14}, "response", success=True)
    assert wp.allProps["cards"][0].energy == 14


@pytest.mark.parametrize("missing", ["n", "e", "i"])
def test_missing_or_null_field_does_not_invent_values(wp, missing):
    status = {"c0n": "Test card", "c0e": 0, "c0i": False}
    status.pop(f"c0{missing}")
    _receive(wp, status)
    assert wp.allProps["cards"][0] is None
    _receive(wp, {f"c0{missing}": None})
    assert wp.allProps["cards"][0] is None


def test_no_card_fields_does_not_create_cards(wp):
    _receive(wp, {"car": 1, "c0p": "{}", "c10n": "Not a supported slot"})
    assert "cards" not in wp.allProps


def test_legacy_cards_are_preserved(wp):
    _receive(wp, {"cards": [{"name": "Legacy card", "energy": 4, "cardId": True}]})
    native = wp.allProps["cards"]
    _receive(wp, {"c0n": "Flat card", "c0e": 5, "c0i": False})
    assert wp.allProps["cards"] is native
    assert native[0].name == "Legacy card"


def test_derived_cards_cannot_be_sent(wp):
    _receive(wp, {"c0n": "Test card", "c0e": 0, "c0i": False})
    with pytest.raises(ValueError, match="read-only"):
        wp.send_update("cards", [])
    wp._wsapp.send.assert_not_called()


def test_native_cards_write_path_is_unchanged(wp):
    _receive(wp, {"cards": []})
    wp.send_update("cards", [])
    assert json.loads(wp._wsapp.send.call_args.args[0])["key"] == "cards"


def test_raw_callbacks_are_preserved(wp):
    callback = mock.Mock()
    wp.register_property_callback(callback)
    _receive(wp, {"c0n": "Test card", "c0e": 0, "c0i": False})
    assert [call.args[0] for call in callback.call_args_list] == ["c0n", "c0e", "c0i"]


@pytest.mark.parametrize("index", range(10))
def test_card_names_masked_without_masking_other_fields(wp, index, caplog):
    status = {f"c{index}n": 'Private "name"', f"c{index}e": 0, f"c{index}i": False, f"c{index}p": "{}"}
    with caplog.at_level("DEBUG"):
        _receive(wp, status)
    assert "Private" not in caplog.text
    assert f'"c{index}n": "***"' in caplog.text
    assert f'"c{index}e": 0' in caplog.text
    assert f'"c{index}i": false' in caplog.text
    assert f'"c{index}p": "{{}}"' in caplog.text
    assert wp.allProps[f"c{index}n"] == 'Private "name"'


@pytest.mark.parametrize("include_list", [False, True])
@pytest.mark.parametrize("index", range(10))
def test_property_debug_masks_only_new_names(index, include_list, caplog):
    utils = sys.modules["custom_components.wattpilot.utils"]
    key = f"c{index}n"
    with caplog.at_level("WARNING"):
        asyncio.run(utils.async_PropertyDebug(key, "Private name", [key] if include_list else True))
        asyncio.run(utils.async_PropertyDebug(f"c{index}e", 0, True))
    assert "Private name" not in caplog.text
    assert f"{key} => ***" in caplog.text
    assert f"c{index}e => 0" in caplog.text


def test_sensor_polling_and_unique_ids_are_compatible(wp, caplog):
    root = pathlib.Path(__file__).parent.parent
    cfg = yaml.safe_load((root / "custom_components/wattpilot/sensor.yaml").read_text())["sensor"]
    cfg = next(item for item in cfg if item["id"] == "cards_0")
    assert "firmware" not in cfg
    hass = mock.MagicMock()
    entry = SimpleNamespace(data={"friendly_name": "TestCharger"}, entry_id="test")
    wp._connected = True
    _receive(wp, {"c0n": "Test card", "c0e": 0, "c0i": False})
    sensor = ChargerSensor(hass, entry, cfg, wp)
    assert sensor._init_failed is False
    assert sensor.available is True
    assert sensor.should_poll is True
    asyncio.run(sensor.async_local_poll())
    assert sensor._attr_native_value == 0
    assert sensor.extra_state_attributes["name"] == "Test card"
    assert sensor.extra_state_attributes["cardId"] is False
    _receive(wp, {"c0n": "Renamed card", "c0e": 17, "c0i": True})
    asyncio.run(sensor.async_local_poll())
    assert sensor._attr_native_value == 17
    assert sensor.extra_state_attributes["name"] == "Renamed card"
    assert sensor.extra_state_attributes["cardId"] is True
    _receive(wp, {"cards": [{"name": "Legacy card", "energy": 17, "cardId": True}]})
    legacy = ChargerSensor(hass, entry, cfg, wp)
    assert legacy._attr_unique_id == sensor._attr_unique_id == "TestCharger-cards_0"
    assert "Test card" not in caplog.text
    assert "Renamed card" not in caplog.text
    wp._connected = False
    assert sensor.available is False


def test_diagnostics_redaction_keys(monkeypatch):
    monkeypatch.setitem(sys.modules, "importlib_metadata", SimpleNamespace(version=mock.Mock()))
    monkeypatch.setitem(sys.modules, "homeassistant.components.diagnostics", SimpleNamespace(async_redact_data=mock.Mock()))
    module = _load_file_as_module("custom_components/wattpilot/diagnostics.py", "custom_components.wattpilot.diagnostics")
    for index in range(10):
        assert f"c{index}n" in module.REDACT_ALLPROPS
        assert all(f"c{index}{suffix}" not in module.REDACT_ALLPROPS for suffix in "eip")
    assert "cards" in module.REDACT_ALLPROPS
