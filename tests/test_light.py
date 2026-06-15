"""Test the Holiday Show Home LED Ball light entity."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
)
from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_info

ENTITY = "light.lab00001ceb11"
DEV_DISCOVERY = (
    "custom_components.lightball.device.bluetooth.async_discovered_service_info"
)
ENTITY_REGISTER = "custom_components.lightball.entity.bluetooth.async_register_callback"


async def _turn_on(hass: HomeAssistant, **attrs) -> None:
    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY, **attrs}, blocking=True
    )


async def test_entity_registered(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The light entity is created and available."""
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.attributes["supported_color_modes"] == ["rgb"]
    assert "MultiColor" in state.attributes["effect_list"]


async def test_turn_on_color(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """An RGB colour maps to the nearest solid palette index, steady mode."""
    await _turn_on(hass, **{ATTR_RGB_COLOR: (255, 0, 0)})
    mock_client.set_state.assert_awaited_once_with(1, 0, 2, turn_on=True, dest=0xEB11)
    assert hass.states.get(ENTITY).state == STATE_ON


async def test_turn_on_brightness(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """HA brightness maps onto the ball's 0-4 level."""
    await _turn_on(hass, **{ATTR_BRIGHTNESS: 255})
    mock_client.set_state.assert_awaited_once_with(1, 0, 4, turn_on=True, dest=0xEB11)


async def test_turn_on_animation_effect(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """An animation effect sends its commonMode mode index."""
    await _turn_on(hass, **{ATTR_EFFECT: "Waves"})
    mock_client.set_state.assert_awaited_once_with(7, 0, 2, turn_on=True, dest=0xEB11)


async def test_turn_on_seasonal_effect(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A seasonal palette uses its colour index with the fade mode."""
    await _turn_on(hass, **{ATTR_EFFECT: "Autumn"})
    mock_client.set_state.assert_awaited_once_with(5, 18, 2, turn_on=True, dest=0xEB11)


async def test_turn_on_show_effect(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A holiday 'show' effect is routed through showView."""
    await _turn_on(hass, **{ATTR_EFFECT: "Christmas"})
    mock_client.set_show.assert_awaited_once_with(0, turn_on=True, dest=0xEB11)
    mock_client.set_state.assert_not_awaited()


async def test_turn_off(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Turning the light off calls the client and clears state."""
    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY}, blocking=True
    )
    mock_client.turn_off.assert_awaited_once()
    assert hass.states.get(ENTITY).state == "off"


async def test_bluetooth_event_pushes_state(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A fresh advertisement triggers a state write."""
    register = MagicMock()
    mock_config_entry.add_to_hass(hass)
    with (
        patch(DEV_DISCOVERY, side_effect=lambda *a, **k: [make_info()]),
        patch(ENTITY_REGISTER, register),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert register.called
    callback = register.call_args[0][1]
    callback(make_info(), None)  # must not raise; pushes a state update
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is not None
