"""Diagnostics support for the Holiday Show Home LED Ball."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import LightBallConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LightBallConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    device = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
        },
        "device": {
            "name": device.name,
            "available": device.available,
        },
    }
