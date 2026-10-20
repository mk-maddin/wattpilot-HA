"""Options flow and setup tests executed against a real Home Assistant core."""

from __future__ import annotations
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "wattpilot"
CONNECT = "custom_components.wattpilot.async_ConnectCharger"


async def _run_local_options_flow(hass, entry, ip_address):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "config_connection"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"connection": "local"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "config_local"
    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"friendly_name": "Wattpilot", "ip_address": ip_address, "password": "pw", "timeout": 5},
    )


async def test_options_flow_in_retry_state_applies_new_config(hass):
    """Reconfiguring an entry that waits for a retry must store the config and retry with it."""
    entry = MockConfigEntry(domain=DOMAIN, data={"connection": "local", "friendly_name": "Wattpilot", "password": "pw"})
    entry.add_to_hass(hass)

    with patch(CONNECT, AsyncMock(return_value=False)) as connect:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert connect.call_count == 1

        result = await _run_local_options_flow(hass, entry, "192.0.2.10")
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

        assert entry.data["ip_address"] == "192.0.2.10"
        assert entry.options["ip_address"] == "192.0.2.10"
        assert connect.call_count == 2
        assert connect.call_args.args[1]["ip_address"] == "192.0.2.10"


async def test_setup_uses_options_when_entry_data_is_empty(hass):
    """Values that are only left in the options must still be used for the connection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"connection": "local", "ip_address": "192.0.2.20", "password": "pw"},
    )
    entry.add_to_hass(hass)

    with patch(CONNECT, AsyncMock(return_value=False)) as connect:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert connect.call_args.args[1]["ip_address"] == "192.0.2.20"


async def test_setup_without_ip_address_is_retried_without_exception(hass):
    """A missing ip address must end in a retry, not in a setup error."""
    entry = MockConfigEntry(domain=DOMAIN, data={"connection": "local", "password": "pw"})
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
