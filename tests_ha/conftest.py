"""Fixtures for tests that run against a real Home Assistant core."""

import pathlib

import custom_components
import pytest

_INTEGRATIONS = str(pathlib.Path(__file__).resolve().parent.parent / "custom_components")
if _INTEGRATIONS not in list(custom_components.__path__):
    custom_components.__path__.append(_INTEGRATIONS)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load the integration from custom_components."""
    yield
