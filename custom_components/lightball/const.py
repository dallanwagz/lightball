"""Constants for the Holiday Show Home LED Ball integration."""

DOMAIN = "lightball"

# CSRmesh GATT bridge service + the two MTL control-point characteristics.
SERVICE_UUID = "0000fef1-0000-1000-8000-00805f9b34fb"
# Split-write: first 20 bytes -> CP1 (...-8003), remainder -> CP2 (...-8004).
CP1_UUID = "c4edc000-9daf-11e3-8003-00025b000b00"
CP2_UUID = "c4edc000-9daf-11e3-8004-00025b000b00"

# Devices advertise a stable local name like "LAB00001CEB11" (the BLE MAC rotates,
# so we identify by name, not address).
NAME_PREFIX = "LAB"

# Network key: reverse(SHA-256(b"686868\x00MCP"))[:16]
PASSPHRASE = b"686868"

# typeId bitmask the app uses for the ball (all products); controller source range.
TYPEID = 0xFFFF

# commonMode mode index (b5): 0=Close(off) 1=Steady 2=Blink ...
MODE_CLOSE = 0
MODE_STEADY = 1
MODE_ON = 255

# Animation effect modes (applied to the current color).
MODES = {
    "Steady": 1, "Blink": 2, "Sparkle": 3, "Instead": 4, "Fade": 5, "Rolling": 6,
    "Waves": 7, "Fireworks": 8, "Polar": 9, "Color Band": 10,
}

# Full palette (commonMode b6) - ColorData.getSTs() in the app.
COLOR_NAMES = [
    "Red", "Green", "Blue", "Orange", "Pink", "Aqua", "Gold", "Fuchsia", "Lawn Green",
    "Magenta", "Cyan", "Yellow", "Purple", "White", "Cold White", "Cool White",
    "Spring", "Summer", "Autumn", "Winter", "Christmas", "Valentine's", "Independence",
    "Thanksgiving", "St. Patrick's", "Halloween", "Sun", "Earth", "MultiColor",
]

# Approx RGB for the 16 solid colors (index 0-15) for nearest-match from HA's wheel.
SOLID_RGB = {
    0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255), 3: (255, 140, 0), 4: (255, 105, 180),
    5: (0, 200, 200), 6: (255, 215, 0), 7: (255, 0, 200), 8: (124, 252, 0),
    9: (255, 0, 255), 10: (0, 255, 255), 11: (255, 255, 0), 12: (150, 0, 200),
    13: (255, 255, 255), 14: (210, 225, 255), 15: (240, 255, 255),
}
# "Shows" = animated presets, sent via showView (byte5=slot 1-3, byte6=show index).
# Order is ColorData.getShowText() in the app.
SHOW_EFFECTS = {
    "Christmas": 0, "Valentine's": 1, "Independence": 2, "Thanksgiving": 3,
    "St. Patrick's": 4, "Halloween": 5, "MultiColor": 6,
}
# Seasonal preset color schemes = genuine commonMode palette colors (not shows).
SEASONAL_COLOR_EFFECTS = {
    "Spring": 16, "Summer": 17, "Autumn": 18, "Winter": 19, "Sun": 26, "Earth": 27,
}

# Effect list = animation modes + shows + seasonal color presets.
EFFECT_LIST = list(MODES) + list(SHOW_EFFECTS) + list(SEASONAL_COLOR_EFFECTS)

# brightness: ball levels 0-4 (wire byte = 4 - level); HA 0-255 maps onto these.
BRIGHT_DEFAULT = 2
