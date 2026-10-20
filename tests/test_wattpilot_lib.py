"""Tests for the internal wattpilot library — websocket message handling."""

from __future__ import annotations
import importlib.util
import json
import pathlib
import sys
import unittest.mock as mock
import pytest

ROOT = pathlib.Path(__file__).parent.parent


def _load_lib():
    """Load the internal library file under a private name with websocket and bcrypt stubbed."""
    stubs = {"websocket": mock.MagicMock(), "bcrypt": mock.MagicMock()}
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(
            "wattpilot_internal_lib",
            ROOT / "custom_components/wattpilot/wattpilot/src/wattpilot/__init__.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def lib():
    return _load_lib()


@pytest.fixture
def wp(lib):
    return lib.Wattpilot(ip="192.0.2.1", password="secret")


class TestOnResponse:

    def test_failed_response_without_request_id_does_not_raise(self, wp):
        wp._Wattpilot__on_message(None, json.dumps({"type": "response", "success": False}))

    def test_failed_response_without_request_id_keeps_connection(self, wp):
        wp._connected = True
        wp._Wattpilot__on_message(None, json.dumps({"type": "response", "success": False}))
        assert wp.connected is True

    def test_failed_response_logs_request_id_and_message(self, wp, caplog):
        payload = {"type": "response", "success": False, "requestId": 7, "message": "denied"}
        with caplog.at_level("ERROR"):
            wp._Wattpilot__on_message(None, json.dumps(payload))
        assert "7" in caplog.text and "denied" in caplog.text


class TestOnMessage:

    def test_malformed_message_does_not_raise_or_disconnect(self, wp):
        wp._connected = True
        wp._Wattpilot__on_message(None, "not json")
        assert wp.connected is True

    def test_message_without_type_does_not_raise(self, wp):
        wp._connected = True
        wp._Wattpilot__on_message(None, json.dumps({"foo": "bar"}))
        assert wp.connected is True

    def test_handler_exception_does_not_reach_error_callback(self, wp):
        wp._connected = True
        wp._property_callback = mock.MagicMock(side_effect=RuntimeError("boom"))
        msg = {"type": "deltaStatus", "status": {"car": 1}}
        wp._Wattpilot__on_message(None, json.dumps(msg))
        assert wp.connected is True


class TestSecretMasking:

    SECRET = "s3cr3t-api-key"

    def test_cak_is_masked_in_message_log(self, wp, caplog):
        msg = {"type": "deltaStatus", "status": {"cak": self.SECRET, "car": 1}}
        with caplog.at_level("DEBUG"):
            wp._Wattpilot__on_message(None, json.dumps(msg))
        assert self.SECRET not in caplog.text
        assert '"cak": "***"' in caplog.text
        assert '"car": 1' in caplog.text

    def test_all_secret_properties_are_masked(self, lib):
        raw = json.dumps({"cak": "a", "ocppck": "b", "ocppcc": "c", "ocppsc": "d", "car": 1})
        masked = lib._mask_secrets(raw)
        assert all(v not in masked for v in ('"a"', '"b"', '"c"', '"d"'))
        assert masked.count('"***"') == 4

    def test_value_with_escaped_quote_is_masked_completely(self, lib):
        raw = json.dumps({"cak": 'ab"cd', "car": 1})
        masked = lib._mask_secrets(raw)
        assert "ab" not in masked and "cd" not in masked

    def test_masking_does_not_change_stored_value(self, wp):
        msg = {"type": "deltaStatus", "status": {"cak": self.SECRET}}
        wp._Wattpilot__on_message(None, json.dumps(msg))
        assert wp.cak == self.SECRET
