"""Fixtures for the Holiday Show Home LED Ball tests."""

from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lightball.const import DOMAIN, SERVICE_UUID

pytest_plugins = "pytest_homeassistant_custom_component"

NAME = "LAB00001CEB11"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading the lightball custom integration in every test."""
    yield


def make_info(
    name: str = NAME, service_uuids: list[str] | None = None
) -> SimpleNamespace:
    """Build a duck-typed Bluetooth service-info for the ball."""
    return SimpleNamespace(
        name=name,
        service_uuids=[SERVICE_UUID] if service_uuids is None else service_uuids,
        service_data={},
        manufacturer_data={},
        address="AA:BB:CC:DD:EE:FF",
        rssi=-50,
        device=SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name=name),
    )


@pytest.fixture
def service_info() -> SimpleNamespace:
    """Return one discovered ball advertisement."""
    return make_info()


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the ball."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=NAME, title=NAME, data={CONF_NAME: NAME}
    )


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Patch the BLE client so no real connection happens; yields the instance."""
    instance = MagicMock()
    instance.set_state = AsyncMock()
    instance.set_show = AsyncMock()
    instance.turn_off = AsyncMock()
    instance.set_ble_device = MagicMock()
    with patch("custom_components.lightball.device.LightBall", return_value=instance):
        yield instance


@pytest.fixture
def mock_discovery() -> Generator[list[SimpleNamespace]]:
    """Report the ball present to device + entity layers; yield the info list."""
    infos = [make_info()]
    with (
        patch(
            "custom_components.lightball.device.bluetooth.async_discovered_service_info",
            side_effect=lambda *a, **k: list(infos),
        ),
        patch(
            "custom_components.lightball.entity.bluetooth.async_register_callback",
            return_value=MagicMock(),
        ),
    ):
        yield infos


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    mock_discovery: list[SimpleNamespace],
) -> MockConfigEntry:
    """Set the integration up and return the loaded config entry."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
