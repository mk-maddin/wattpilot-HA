"""Diagnostics tests executed against a real Home Assistant core."""

from __future__ import annotations
from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wattpilot.diagnostics import async_get_config_entry_diagnostics

DOMAIN = "wattpilot"


async def test_diagnostics_redacts_secrets_and_card_names(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"connection": "local", "ip_address": "192.0.2.1", "password": "pw"})
    entry.add_to_hass(hass)
    charger = SimpleNamespace(
        allProps={
            "cak": "s3cr3t-api-key",
            "cards": [{"name": "Private Name", "energy": 1}],
            "car": 1,
        }
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"charger": charger}

    diag = await async_get_config_entry_diagnostics(hass, entry)

    text = str(diag)
    assert "s3cr3t-api-key" not in text
    assert "Private Name" not in text
    assert diag["charger_properties"]["car"] == 1
