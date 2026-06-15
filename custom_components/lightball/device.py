"""HA-side glue for the LED Ball: resolve the rotating address and send commands.

The ball advertises a stable local name but rotates its BLE address, so we never
pin a MAC; we look up the current advertisement by name through Home Assistant's
Bluetooth manager (which transparently includes ESPHome BT proxies) and hand a
fresh ``BLEDevice`` to the ``lightball_ble`` client before each command.
"""

from __future__ import annotations

import logging

from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from lightball_ble import LightBall

_LOGGER = logging.getLogger(__name__)


def _device_id_from_name(name: str) -> int:
    """Mesh device address from the stable name.

    The address is the low 16 bits of the name's hex suffix, forced into the
    CSRmesh device-address class (top bits ``0xC000``). Without this a name whose
    suffix lands in ``0x8000``-``0xBFFF`` (the controller/group class) would be
    treated as a controller and broadcast to every ball instead of addressing one.
    Examples: ``LAB00001E8B32`` -> ``0x8B32`` -> ``0xCB32``; ``LAB00001CEB11`` ->
    ``0xEB11`` (already device-class, unchanged). Returns 0 (broadcast) if not hex.
    """
    try:
        return int(name[-4:], 16) | 0xC000
    except ValueError:
        return 0


class LightBallDevice:
    """Resolve an LED Ball by its stable name and proxy commands to the BLE client."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        """Initialize the device wrapper."""
        self.hass = hass
        self.name = name
        # The mesh address is the low 16 bits of the device name's hex suffix, so a
        # command reaches only this ball even though all balls share a network key.
        self.device_id = _device_id_from_name(name)
        self._client: LightBall | None = None

    def _current_device(self) -> BLEDevice | None:
        """Return the BLEDevice currently advertising under our name (any address)."""
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            if info.name == self.name:
                return info.device
        return None

    @property
    def available(self) -> bool:
        """Whether the ball is currently visible to HA Bluetooth."""
        return self._current_device() is not None

    def _client_for_current_device(self) -> LightBall:
        """Return a client bound to the ball's current address."""
        ble_device = self._current_device()
        if ble_device is None:
            raise LightBallNotFound(self.name)
        if self._client is None:
            self._client = LightBall(ble_device, self.name)
        else:
            self._client.set_ble_device(ble_device)
        return self._client

    async def set_state(
        self, mode: int, color: int, level: int, *, turn_on: bool = True
    ) -> None:
        """Apply an animation mode + palette colour + brightness to this ball only."""
        await self._client_for_current_device().set_state(
            mode, color, level, turn_on=turn_on, dest=self.device_id
        )

    async def set_show(self, show_sel: int, *, turn_on: bool = True) -> None:
        """Activate an animated 'show' preset on this ball only."""
        await self._client_for_current_device().set_show(
            show_sel, turn_on=turn_on, dest=self.device_id
        )

    async def turn_off(self) -> None:
        """Turn this ball off."""
        await self._client_for_current_device().turn_off(dest=self.device_id)


class LightBallNotFound(RuntimeError):
    """Raised when the ball is not currently visible to HA Bluetooth."""

    def __init__(self, name: str) -> None:
        """Initialize the error."""
        super().__init__(f"{name} is not currently visible to Home Assistant Bluetooth")
