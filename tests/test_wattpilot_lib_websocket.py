"""End-to-end tests for the internal wattpilot library against a fake charger websocket."""

from __future__ import annotations
import asyncio
import hashlib
import hmac
import importlib.util
import json
import pathlib
import threading
import unittest.mock as mock
import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web  # noqa: E402

ROOT = pathlib.Path(__file__).parent.parent
SERIAL = "12345678"
PASSWORD = "secret"


def _load_lib():
    """Load the internal library with the real aiohttp and bcrypt."""
    spec = importlib.util.spec_from_file_location(
        "wattpilot_internal_lib_ws",
        ROOT / "custom_components/wattpilot/wattpilot/src/wattpilot/__init__.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCharger:
    """A minimal Wattpilot websocket server: hello, auth, status and setValue."""

    def __init__(self, lib, password=PASSWORD, hash_type="pbkdf2", secured=1, binary=False, silent=False):
        self.lib = lib
        self.hash_type = hash_type
        self.secured = secured
        self.binary = binary
        self.silent = silent
        self.hashed = lib._hash_password(password, SERIAL, hash_type)
        self.connections = 0
        self.received = []
        self.sockets = []
        self.origins = []

    async def send(self, ws, data):
        if self.binary:
            await ws.send_bytes(json.dumps(data).encode())
        else:
            await ws.send_json(data)

    async def handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        self.sockets.append(ws)
        self.origins.append(request.headers.get("Origin"))
        await self.send(ws, {"type": "hello", "serial": SERIAL, "hostname": "wattpilot_test", "manufacturer": "fronius", "devicetype": "wattpilot", "protocol": 2, "secured": self.secured})
        await self.send(ws, {"type": "authRequired", "token1": "t1", "token2": "t2", "hash": self.hash_type})
        async for message in ws:
            data = json.loads(message.data)
            self.received.append(data)
            if data["type"] == "auth":
                hash1 = hashlib.sha256(b"t1" + self.hashed).hexdigest()
                expected = hashlib.sha256((data["token3"] + "t2" + hash1).encode()).hexdigest()
                if data["hash"] != expected:
                    await self.send(ws, {"type": "authError", "message": "Wrong password"})
                    continue
                await self.send(ws, {"type": "authSuccess"})
                await self.send(ws, {"type": "fullStatus", "partial": False, "status": {"amp": 16, "car": 1, "cards": [{"name": "card", "energy": 5}]}})
                if not self.silent:
                    await self.send(ws, {"type": "deltaStatus", "status": {"rbt": 1000}})
            elif data["type"] == "setValue":
                await self.send(ws, {"type": "response", "success": True, "requestId": data["requestId"], "status": {data["key"]: data["value"]}})
            elif data["type"] == "securedMsg":
                mac = hmac.new(bytearray(self.hashed), bytearray(data["data"].encode()), hashlib.sha256).hexdigest()
                inner = json.loads(data["data"])
                if mac != data["hmac"]:
                    await ws.send_json({"type": "response", "success": False, "requestId": data["requestId"], "message": "hmac"})
                    continue
                await ws.send_json({"type": "response", "success": True, "requestId": data["requestId"], "status": {inner["key"]: inner["value"]}})
        return ws


@pytest.fixture
def lib():
    return _load_lib()


async def _serve(fake):
    app = web.Application()
    app.router.add_get("/ws", fake.handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"127.0.0.1:{site._server.sockets[0].getsockname()[1]}"


@pytest.fixture
async def charger_server(lib):
    fake = FakeCharger(lib)
    app = web.Application()
    app.router.add_get("/ws", fake.handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield fake, f"127.0.0.1:{port}"
    await runner.cleanup()


async def _wait_for(condition, timeout=5.0):
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_connects_authenticates_and_receives_status(lib, charger_server):
    fake, host = charger_server
    updates = []
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.register_property_callback(lambda name, value: updates.append((name, value)))
    wp.connect()
    try:
        await _wait_for(lambda: wp.connected and wp.allPropsInitialized)
        assert wp.serial == SERIAL
        assert wp.allProps["amp"] == 16
        assert wp.allProps["cards"][0].name == "card"
        await _wait_for(lambda: ("rbt", 1000) in updates)
        assert ("amp", 16) in updates
    finally:
        await wp.async_disconnect()
    assert not wp.connected
    assert wp._task.done()


@pytest.mark.asyncio
async def test_password_hash_runs_outside_the_event_loop(lib, charger_server):
    fake, host = charger_server
    threads = []
    original = lib._hash_password

    def recording_hash(*args):
        threads.append(threading.get_ident())
        return original(*args)

    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    with mock.patch.object(lib, "_hash_password", recording_hash):
        wp.connect()
        try:
            await _wait_for(lambda: wp.connected)
        finally:
            await wp.async_disconnect()
    assert threads and threading.get_ident() not in threads


@pytest.mark.asyncio
async def test_secured_set_value_is_signed_and_applied(lib, charger_server):
    fake, host = charger_server
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.connect()
    try:
        await _wait_for(lambda: wp.connected and wp.allPropsInitialized)
        await wp.async_send_update("amp", 10)
        await _wait_for(lambda: wp.allProps["amp"] == 10)
        secured = [m for m in fake.received if m["type"] == "securedMsg"]
        assert len(secured) == 1
        assert json.loads(secured[0]["data"]) == {"type": "setValue", "requestId": 1, "key": "amp", "value": 10}
    finally:
        await wp.async_disconnect()


@pytest.mark.asyncio
async def test_send_without_connection_raises(lib):
    wp = lib.Wattpilot(ip="192.0.2.1", password=PASSWORD)
    with pytest.raises(ConnectionError):
        await wp.async_send_update("amp", 10)


@pytest.mark.asyncio
async def test_reconnects_after_the_charger_closes_the_socket(lib, charger_server):
    fake, host = charger_server
    updates = []
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.register_property_callback(lambda name, value: updates.append((name, value)))
    with mock.patch.object(lib, "RECONNECT_SECONDS", 0.05):
        wp.connect()
        try:
            await _wait_for(lambda: wp.connected)
            await fake.sockets[0].close()
            await _wait_for(lambda: (lib.CONST_CONNECTION_SENTINEL, False) in updates)
            await _wait_for(lambda: fake.connections == 2 and wp.connected)
        finally:
            await wp.async_disconnect()


@pytest.mark.asyncio
async def test_wrong_password_does_not_connect(lib, charger_server):
    fake, host = charger_server
    wp = lib.Wattpilot(ip=host, password="wrong")
    with mock.patch.object(lib, "RECONNECT_SECONDS", 30):
        wp.connect()
        try:
            await _wait_for(lambda: any(m["type"] == "auth" for m in fake.received))
            await asyncio.sleep(0.2)
            assert not wp.connected
        finally:
            await wp.async_disconnect()


@pytest.mark.asyncio
async def test_unreachable_charger_does_not_raise_and_disconnect_ends_the_task(lib):
    wp = lib.Wattpilot(ip="127.0.0.1:9", password=PASSWORD)
    with mock.patch.object(lib, "RECONNECT_SECONDS", 30):
        wp.connect()
        await asyncio.sleep(0.2)
        assert not wp.connected
        await wp.async_disconnect()
    assert wp._task.done()


@pytest.mark.asyncio
async def test_uses_a_given_session_and_leaves_it_open(lib, charger_server):
    fake, host = charger_server
    async with aiohttp.ClientSession() as session:
        wp = lib.Wattpilot(ip=host, password=PASSWORD, session=session)
        wp.connect()
        try:
            await _wait_for(lambda: wp.connected)
        finally:
            await wp.async_disconnect()
        assert not session.closed


@pytest.mark.parametrize("hash_type", ["pbkdf2", "bcrypt"])
async def test_both_hash_types_authenticate(lib, hash_type):
    fake = FakeCharger(lib, hash_type=hash_type)
    runner, host = await _serve(fake)
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.connect()
    try:
        await _wait_for(lambda: wp.connected and wp.allPropsInitialized)
    finally:
        await wp.async_disconnect()
        await runner.cleanup()


async def test_unsecured_set_value_is_sent_plain(lib):
    fake = FakeCharger(lib, secured=0)
    runner, host = await _serve(fake)
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.connect()
    try:
        await _wait_for(lambda: wp.connected and wp.allPropsInitialized)
        await wp.async_send_update("amp", 8)
        await _wait_for(lambda: wp.allProps["amp"] == 8)
        assert [m["type"] for m in fake.received] == ["auth", "setValue"]
    finally:
        await wp.async_disconnect()
        await runner.cleanup()


async def test_binary_frames_are_read_like_text(lib):
    fake = FakeCharger(lib, binary=True)
    runner, host = await _serve(fake)
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.connect()
    try:
        await _wait_for(lambda: wp.connected and wp.allPropsInitialized)
        assert wp.allProps["amp"] == 16
    finally:
        await wp.async_disconnect()
        await runner.cleanup()


async def test_origin_header_is_sent_like_websocket_client(lib, charger_server):
    fake, host = charger_server
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.connect()
    try:
        await _wait_for(lambda: wp.connected)
        assert fake.origins == [f"http://{host}"]
    finally:
        await wp.async_disconnect()


async def test_silent_charger_is_dropped_and_reconnected(lib, caplog):
    fake = FakeCharger(lib, silent=True)
    runner, host = await _serve(fake)
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    with mock.patch.object(lib, "CONST_RECEIVE_TIMEOUT_SECONDS", 0.3), mock.patch.object(lib, "RECONNECT_SECONDS", 0.05):
        wp.connect()
        try:
            await _wait_for(lambda: fake.connections >= 2 and wp.connected)
        finally:
            await wp.async_disconnect()
            await runner.cleanup()
    assert "no message from the charger for 0.3 seconds" in caplog.text


async def test_closed_session_ends_the_task(lib, charger_server):
    fake, host = charger_server
    session = aiohttp.ClientSession()
    wp = lib.Wattpilot(ip=host, password=PASSWORD, session=session)
    with mock.patch.object(lib, "RECONNECT_SECONDS", 0.05):
        wp.connect()
        await _wait_for(lambda: wp.connected)
        await session.close()
        await _wait_for(lambda: wp._task.done())
    assert not wp.connected


async def test_cancelling_the_caller_of_async_disconnect_propagates(lib, charger_server):
    fake, host = charger_server
    wp = lib.Wattpilot(ip=host, password=PASSWORD)
    wp.connect()
    await _wait_for(lambda: wp.connected)
    caller = asyncio.get_running_loop().create_task(wp.async_disconnect())
    await asyncio.sleep(0)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await _wait_for(lambda: wp._task.done())
