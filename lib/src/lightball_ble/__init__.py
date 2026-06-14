"""CSRmesh BLE protocol and client for Holiday Show Home LED Balls."""

from __future__ import annotations

from .client import LightBall
from .protocol import (
    CP1_UUID,
    CP2_UUID,
    MODE_CLOSE,
    MODE_ON,
    MODE_STEADY,
    SERVICE_UUID,
    derive_key,
    make_packet,
)

__all__ = [
    "LightBall",
    "SERVICE_UUID",
    "CP1_UUID",
    "CP2_UUID",
    "MODE_CLOSE",
    "MODE_ON",
    "MODE_STEADY",
    "derive_key",
    "make_packet",
]
