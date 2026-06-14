"""Light platform for the Holiday Show Home LED Ball."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BRIGHT_DEFAULT,
    DOMAIN,
    EFFECT_LIST,
    MODE_STEADY,
    MODES,
    SEASONAL_COLOR_EFFECTS,
    SEASONAL_MODE,
    SHOW_EFFECTS,
    SOLID_RGB,
)
from .device import LightBallDevice


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LED Ball light from a config entry."""
    device: LightBallDevice = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LightBallLight(device, entry)])


def _nearest_solid(rgb: tuple[int, int, int]) -> int:
    return min(SOLID_RGB, key=lambda i: sum((a - c) ** 2 for a, c in zip(SOLID_RGB[i], rgb)))


def _ha_to_level(v: int) -> int:
    return max(0, min(4, round(v / 255 * 4)))


def _level_to_ha(level: int) -> int:
    return round(level / 4 * 255)


class LightBallLight(LightEntity):
    """A Holiday Show Home LED Ball as an HA light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = EFFECT_LIST

    def __init__(self, device: LightBallDevice, entry: ConfigEntry) -> None:
        self._device = device
        self._attr_unique_id = entry.unique_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.unique_id)},
            "name": entry.title,
            "manufacturer": "Willis Electric / Kupoint",
            "model": "Show Home App Light Ball (AL96, CSRmesh)",
        }
        # optimistic state (the ball isn't reliably readable)
        self._attr_is_on = False
        self._attr_brightness = _level_to_ha(BRIGHT_DEFAULT)
        self._attr_rgb_color = (255, 0, 0)
        self._attr_effect = "Steady"
        self._color = 0
        self._mode = MODE_STEADY
        self._level = BRIGHT_DEFAULT

    @property
    def available(self) -> bool:
        return self._device.available

    async def async_turn_on(self, **kwargs: Any) -> None:
        show: int | None = None
        if ATTR_BRIGHTNESS in kwargs:
            self._level = _ha_to_level(kwargs[ATTR_BRIGHTNESS])
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_RGB_COLOR in kwargs:
            self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
            self._color = _nearest_solid(kwargs[ATTR_RGB_COLOR])
            self._mode = MODE_STEADY
            self._attr_effect = "Steady"
        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            self._attr_effect = effect
            if effect in MODES:                       # animation mode on current color
                self._mode = MODES[effect]
            elif effect in SEASONAL_COLOR_EFFECTS:    # multi-color palette, fade through it
                self._color = SEASONAL_COLOR_EFFECTS[effect]
                self._mode = SEASONAL_MODE
            elif effect in SHOW_EFFECTS:              # animated 'show' preset (showView)
                show = SHOW_EFFECTS[effect]

        if show is not None:
            await self._device.set_show(show, turn_on=True)
        else:
            await self._device.set_state(self._mode, self._color, self._level, turn_on=True)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.turn_off()
        self._attr_is_on = False
        self.async_write_ha_state()
