"""Setup, push updates and unload against a fake charger websocket, with a real Home Assistant core."""

from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import threading

import pytest
from aiohttp import web
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "wattpilot"
SERIAL = "12345678"
PASSWORD = "pw"
STATUS = {"car": 1, "amp": 16, "wh": 5, "var": 11, "typ": "Wattpilot", "fwv": "40.7", "rbt": 1000, "nrg": [230, 231, 229, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}


class FakeCharger:

    def __init__(self):
        self.hashed = base64.b64encode(hashlib.pbkdf2_hmac("sha512", PASSWORD.encode(), SERIAL.encode(), 100000, 256))[:32]
        self.sockets = []

    async def handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        await ws.send_json({"type": "hello", "serial": SERIAL, "hostname": "wattpilot_test", "manufacturer": "fronius", "devicetype": "wattpilot", "protocol": 2, "secured": 1})
        await ws.send_json({"type": "authRequired", "token1": "t1", "token2": "t2", "hash": "pbkdf2"})
        async for message in ws:
            data = json.loads(message.data)
            if data["type"] == "auth":
                await ws.send_json({"type": "authSuccess"})
                await ws.send_json({"type": "fullStatus", "partial": False, "status": STATUS})
        return ws


async def _start(fake):
    app = web.Application()
    app.router.add_get("/ws", fake.handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"127.0.0.1:{site._server.sockets[0].getsockname()[1]}"


async def _wait_for(condition, timeout=10.0):
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.05)


def _state(hass, name):
    return next((s for s in hass.states.async_all() if s.attributes.get("friendly_name", "").endswith(name)), None)


@pytest.mark.usefixtures("socket_enabled")
async def test_setup_push_and_unload_without_threads(hass):
    """The charger connects on the event loop, pushes reach entities and unload ends the websocket task."""
    fake = FakeCharger()
    runner, host = await _start(fake)
    entry = MockConfigEntry(domain=DOMAIN, data={"connection": "local", "friendly_name": "Wattpilot", "ip_address": host, "password": PASSWORD, "timeout": 10})
    entry.add_to_hass(hass)
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED

        charger = hass.data[DOMAIN][entry.entry_id]["charger"]
        assert charger.connected
        assert charger.allProps["wh"] == 5

        await fake.sockets[0].send_json({"type": "deltaStatus", "status": {"wh": 12, "rbt": 2000}})
        await _wait_for(lambda: getattr(_state(hass, "Connection Charged"), "state", None) == "12")

        task = charger._task
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert task.done()
        assert not any(t.name == "wattpilot-ws-supervisor" for t in threading.enumerate())
    finally:
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
        await runner.cleanup()
