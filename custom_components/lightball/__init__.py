"""The Holiday Show Home LED Ball integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .device import LightBallDevice

PLATFORMS: list[Platform] = [Platform.LIGHT]

type LightBallConfigEntry = ConfigEntry[LightBallDevice]


async def async_setup_entry(hass: HomeAssistant, entry: LightBallConfigEntry) -> bool:
    """Set up an LED Ball from a config entry."""
    name = entry.data[CONF_NAME]
    device = LightBallDevice(hass, name)
    if not device.available:
        raise ConfigEntryNotReady(
            f"{name} is not currently visible to Home Assistant Bluetooth"
        )

    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LightBallConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
