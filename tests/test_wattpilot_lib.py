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
