"""Constants for the Holiday Show Home LED Ball integration."""

from __future__ import annotations

from lightball_ble import MODE_STEADY, SERVICE_UUID

DOMAIN = "lightball"

# Re-exported from the library so the integration has a single source of truth.
__all__ = ["DOMAIN", "SERVICE_UUID", "MODE_STEADY"]

# Devices advertise a stable local name like "LAB00001CEB11" (the BLE MAC rotates,
# so we identify by name, not address).
NAME_PREFIX = "LAB"

# --- presentation: effect names mapped to the device's protocol indices ----------
# Animation modes applied to the current colour (commonMode mode index).
MODES = {
    "Steady": 1,
    "Blink": 2,
    "Sparkle": 3,
    "Instead": 4,
    "Fade": 5,
    "Rolling": 6,
    "Waves": 7,
    "Fireworks": 8,
    "Polar": 9,
    "Color Band": 10,
}

# Animated "shows" sent via showView (show index).
SHOW_EFFECTS = {
    "Christmas": 0,
    "Valentine's": 1,
    "Independence": 2,
    "Thanksgiving": 3,
    "St. Patrick's": 4,
    "Halloween": 5,
    "MultiColor": 6,
}

# Seasonal palettes are multi-colour commonMode colours; pairing them with a dynamic
# mode (Fade) makes the ball actively transition through the scheme.
SEASONAL_COLOR_EFFECTS = {
    "Spring": 16,
    "Summer": 17,
    "Autumn": 18,
    "Winter": 19,
    "Sun": 26,
    "Earth": 27,
}
SEASONAL_MODE = 5  # Fade

EFFECT_LIST = [*MODES, *SHOW_EFFECTS, *SEASONAL_COLOR_EFFECTS]

# Approx RGB for the 16 solid palette colours (index 0-15) for nearest-match.
SOLID_RGB: dict[int, tuple[int, int, int]] = {
    0: (255, 0, 0),
    1: (0, 255, 0),
    2: (0, 0, 255),
    3: (255, 140, 0),
    4: (255, 105, 180),
    5: (0, 200, 200),
    6: (255, 215, 0),
    7: (255, 0, 200),
    8: (124, 252, 0),
    9: (255, 0, 255),
    10: (0, 255, 255),
    11: (255, 255, 0),
    12: (150, 0, 200),
    13: (255, 255, 255),
    14: (210, 225, 255),
    15: (240, 255, 255),
}

# Ball brightness levels are 0-4; HA's 0-255 maps onto these. Default = level 2.
BRIGHT_DEFAULT = 2
