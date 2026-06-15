"""Test setup, teardown and the device wrapper for the LED Ball."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lightball.device import LightBallDevice, LightBallNotFound
from custom_components.lightball.diagnostics import async_get_config_entry_diagnostics

from .conftest import NAME, make_info

DEV_DISCOVERY = (
    "custom_components.lightball.device.bluetooth.async_discovered_service_info"
)


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The entry loads, exposes runtime_data, then unloads cleanly."""
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, LightBallDevice)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready_when_not_visible(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Setup is retried when the ball is not currently visible to Bluetooth."""
    mock_config_entry.add_to_hass(hass)
    with patch(DEV_DISCOVERY, return_value=[]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Diagnostics summarize the entry and device."""
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["unique_id"] == NAME
    assert diag["device"]["name"] == NAME
    assert diag["device"]["available"] is True


async def test_device_available_matches_name(hass: HomeAssistant) -> None:
    """Availability reflects whether the stable name is currently advertising."""
    device = LightBallDevice(hass, NAME)
    with patch(DEV_DISCOVERY, return_value=[make_info()]):
        assert device.available is True
    with patch(DEV_DISCOVERY, return_value=[make_info(name="OTHER")]):
        assert device.available is False
    with patch(DEV_DISCOVERY, return_value=[]):
        assert device.available is False


async def test_device_not_found_raises(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Commands raise when the ball is not visible."""
    device = LightBallDevice(hass, NAME)
    with patch(DEV_DISCOVERY, return_value=[]), pytest.raises(LightBallNotFound):
        await device.turn_off()


async def test_device_reuses_client(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A second command refreshes the BLEDevice on the existing client."""
    device = LightBallDevice(hass, NAME)
    with patch(DEV_DISCOVERY, return_value=[make_info()]):
        await device.set_state(1, 0, 2)
        await device.set_show(0)
    mock_client.set_state.assert_awaited_once_with(1, 0, 2, turn_on=True, dest=0xEB11)
    mock_client.set_show.assert_awaited_once_with(0, turn_on=True, dest=0xEB11)
    # First call constructed the client; the second refreshed its address.
    mock_client.set_ble_device.assert_called_once()


def test_device_id_from_name() -> None:
    """The mesh address is the low 16 bits of the name; non-hex falls back to 0."""
    from custom_components.lightball.device import _device_id_from_name

    assert _device_id_from_name("LAB00001CEB11") == 0xEB11
    assert _device_id_from_name("LAB00001EE5D5") == 0xE5D5
    assert _device_id_from_name("lightballZZZZ") == 0
