"""
conftest.py — shared fixtures and import bootstrap for all Wattpilot tests.

Strategy: We use importlib.util.spec_from_file_location to load the individual
submodule files directly (bypassing the package __init__.py which has deep HA
dependencies). All HA and wattpilot stdlib imports are stubbed via sys.modules
before any integration code is loaded.
"""

from __future__ import annotations
import sys
import types
import asyncio
import importlib.util
import pathlib
import unittest.mock as mock
import pytest

ROOT = pathlib.Path(__file__).parent.parent  # repo root

# ---------------------------------------------------------------------------
# Build comprehensive HA stubs — must be done ONCE before any integration
# module is loaded.
# ---------------------------------------------------------------------------

STATE_UNKNOWN = "unknown"

def _stub_module(name: str, **attrs) -> types.ModuleType:
    """Create and register a stub module in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _EntityCategory:
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
    SYSTEM = "system"
    def __init__(self, v): self.value = v
    def __repr__(self): return f"EntityCategory({self.value})"


class _Entity:
    """Minimal HA Entity stub."""
    async_write_ha_state = mock.MagicMock()
    enabled = True


class _SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"
    def __init__(self, v): self._v = v


class _Version:
    def __init__(self, v):
        self._t = tuple(int(x) for x in str(v).split("."))
    def __ge__(self, o): return self._t >= o._t
    def __le__(self, o): return self._t <= o._t
    def __gt__(self, o): return self._t > o._t
    def __lt__(self, o): return self._t < o._t
    def __eq__(self, o): return self._t == o._t


# HA const
_stub_module("homeassistant.const",
    CONF_FRIENDLY_NAME="friendly_name",
    CONF_IP_ADDRESS="host",
    CONF_PARAMS="params",
    CONF_PASSWORD="password",
    CONF_TIMEOUT="timeout",
    STATE_UNKNOWN=STATE_UNKNOWN,
)
# HA core
_stub_module("homeassistant.core", HomeAssistant=object)
# HA config_entries
_stub_module("homeassistant.config_entries", ConfigEntry=object)
# HA loader
_stub_module("homeassistant.loader", async_get_integration=mock.AsyncMock())
# HA helpers
_stub_module("homeassistant.helpers")
_stub_module("homeassistant.helpers.entity",
    Entity=_Entity,
    EntityCategory=_EntityCategory,
    DeviceInfo=dict,
)
_stub_module("homeassistant.helpers.device_registry")
# HA components
_stub_module("homeassistant.components")
_stub_module("homeassistant.components.sensor",
    SensorStateClass=_SensorStateClass,
    SensorEntity=_Entity,
    UNIT_CONVERTERS={},
)
# HA root
_stub_module("homeassistant",
    core=sys.modules["homeassistant.core"],
    const=sys.modules["homeassistant.const"],
)

# packaging
_stub_module("packaging")
_stub_module("packaging.version", Version=_Version)

# wattpilot
_wattpilot_stub = _stub_module("wattpilot", Wattpilot=object,
                                __file__="<stub>", __version__="0.2.2")

# aiofiles (used by sensor.py / yaml loading)
import unittest.mock as _mock
_aiofiles = _stub_module("aiofiles")
_aiofiles.open = _mock.MagicMock()

# yaml
import yaml as _real_yaml
_stub_module("yaml", safe_load=_real_yaml.safe_load)


# ---------------------------------------------------------------------------
# Stub the custom_components.wattpilot.* package entries
# ---------------------------------------------------------------------------

def _stub_const():
    m = _stub_module("custom_components.wattpilot.const",
        CONF_CHARGER="charger",
        CONF_CONNECTION="connection",
        CONF_CLOUD="cloud",
        CONF_DBG_PROPS="debug_properties",
        CONF_LOCAL="local",
        CONF_PUSH_ENTITIES="push_entities",
        CONF_SERIAL="serial",
        DEFAULT_NAME="Wattpilot",
        DEFAULT_TIMEOUT=15,
        DOMAIN="wattpilot",
        WATTPILOT_CONNECTION_SENTINEL="__wattpilot_connection__",
        EVENT_PROPS_ID="wattpilot_property_message",
        EVENT_PROPS=["ftt", "cak"],
        CLOUD_API_URL_PREFIX="https://",
        CLOUD_API_URL_POSTFIX=".api.v3.go-e.io/api/",
        FUNC_OPTION_UPDATES="options_update_listener",
        FUNC_PROPERTY_UPDATES_CALLBACK="property_updates_callback",
        SUPPORTED_PLATFORMS=["button", "number", "select", "sensor", "switch", "update"],
    )
    return m


def _load_file_as_module(rel_path: str, module_name: str):
    """
    Load a .py file directly by filesystem path, register it under the given
    module name.  This bypasses the package __init__.py entirely.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    file_path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub the package __init__ so submodule imports don't trigger it
_pkg_stub = _stub_module("custom_components")
_pkg_stub2 = _stub_module("custom_components.wattpilot")
_stub_const()

# Load utils first (entities.py depends on it)
_utils_mod = _load_file_as_module(
    "custom_components/wattpilot/utils.py",
    "custom_components.wattpilot.utils",
)
# Load entities
_entities_mod = _load_file_as_module(
    "custom_components/wattpilot/entities.py",
    "custom_components.wattpilot.entities",
)
# Load sensor
_sensor_mod = _load_file_as_module(
    "custom_components/wattpilot/sensor.py",
    "custom_components.wattpilot.sensor",
)

# Expose for tests
GetChargerProp = _utils_mod.GetChargerProp
async_GetChargerProp = _utils_mod.async_GetChargerProp
ChargerPlatformEntity = _entities_mod.ChargerPlatformEntity
ChargerSensor = _sensor_mod.ChargerSensor


# ---------------------------------------------------------------------------
# Mock charger
# ---------------------------------------------------------------------------

import types as _types


class MockCharger:
    """Minimal mock of a connected wattpilot.Wattpilot charger."""

    def __init__(self, extra_props=None, has_cards=True):
        self.connected = True
        self.allPropsInitialized = True
        self.serial = "TEST12345"
        self.manufacturer = "Fronius"
        self.name = "Test Wattpilot"
        self.hostname = "wattpilot.local"
        self.firmware = "41.0"
        self.devicetype = "Wattpilot 11"

        base_props = {
            "car": 1,
            "err": 0,
            "eto": 12345,
            "wh": 100,
            "nrg": [230, 230, 230, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "tma": [35.5, 36.0],
            "rssi": -65,
            "rbc": 3,
            "rbt": 123456789,
            "modelStatus": 3,
            "wst": 3,
            "var": 11,
            "sse": "TEST12345",
            "typ": "Wattpilot 11J",
            "onv": "41.0",
            "ccw": _types.SimpleNamespace(
                ssid="MyWifi", ip="192.168.1.100",
                netmask="255.255.255.0", gw="192.168.1.1",
                channel=6, bssid="AA:BB:CC:DD:EE:FF",
            ),
        }

        if has_cards:
            base_props["cards"] = [
                _types.SimpleNamespace(name="Card0", cardId="abc", energy=500),
                _types.SimpleNamespace(name="Card1", cardId="def", energy=200),
            ]

        if extra_props:
            base_props.update(extra_props)

        self.allProps = base_props

    # Attributes accessed via hasattr/getattr
    AccessState = "auto"
    carConnected = "no car"


class MockChargerMissingProps(MockCharger):
    """Charger missing optional properties: upo, cus, ffb, lck, cards."""
    def __init__(self):
        super().__init__(has_cards=False)


@pytest.fixture
def charger():
    return MockCharger()


@pytest.fixture
def charger_no_optional():
    return MockChargerMissingProps()
