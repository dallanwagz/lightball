"""Test the Holiday Show Home LED Ball config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lightball.const import DOMAIN

from .conftest import NAME, make_info

DISCOVERY = "custom_components.lightball.config_flow.async_discovered_service_info"


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """A ball seen by Bluetooth can be added via the user flow."""
    with patch(DISCOVERY, return_value=[make_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: NAME}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_NAME: NAME}
    assert result["result"].unique_id == NAME


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    """The user flow aborts when no balls are visible."""
    with patch(DISCOVERY, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_filters_other_devices(hass: HomeAssistant) -> None:
    """Non-ball advertisements are not offered (and yield no_devices_found)."""
    other = make_info(name="LAP-V201S-WUS", service_uuids=[])
    with patch(DISCOVERY, return_value=[other]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """Submitting a name that becomes configured aborts as already_configured."""
    with patch(DISCOVERY, return_value=[make_info()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        # The entry appears between showing the form and submitting it.
        mock_config_entry.add_to_hass(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: NAME}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_discovery_flow(hass: HomeAssistant) -> None:
    """A discovered ball can be confirmed and added."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_NAME: NAME}
    assert result["result"].unique_id == NAME


async def test_bluetooth_discovery_not_supported(hass: HomeAssistant) -> None:
    """A non-ball advertisement is rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=make_info(name="Some Other Device", service_uuids=[]),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_no_name(hass: HomeAssistant) -> None:
    """An advertisement without a local name is rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_info(name="")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_already_configured(
    hass: HomeAssistant, mock_config_entry
) -> None:
    """A discovered ball that is already configured aborts."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
