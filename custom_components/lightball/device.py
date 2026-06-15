"""HA-side glue for the LED Ball: resolve the rotating address and send commands.

The ball advertises a stable local name but rotates its BLE address, so we never
pin a MAC; we look it up by name through Home Assistant's Bluetooth manager (which
includes ESPHome BT proxies) and hand a fresh ``BLEDevice`` to the ``lightball_ble``
client, addressing the command to the ball's mesh id.

Some balls ship with a mesh id in the controller class (``0x8000``-``0xBFFF``).
Such a ball, when it is the directly-connected GATT bridge, re-broadcasts commands
to the whole mesh and hijacks every other ball. As a *relayed* leaf it behaves
normally, so we route a controller-class ball's commands through a different,
device-class ball's connection instead of connecting to it directly.
"""

from __future__ import annotations

import logging

from bleak.backends.device import BLEDevice
from lightball_ble import LightBall

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import NAME_PREFIX

_LOGGER = logging.getLogger(__name__)


def _device_id_from_name(name: str) -> int:
    """Mesh device address = low 16 bits of the name's hex suffix.

    e.g. ``LAB00001CEB11`` -> ``0xEB11``. Returns 0 (broadcast) if not hex.
    """
    try:
        return int(name[-4:], 16)
    except ValueError:
        return 0


def _is_device_class(device_id: int) -> bool:
    """Device-class ids (``0xC000``-``0xFFFF``) are safe to connect to directly."""
    return device_id & 0xC000 == 0xC000


class LightBallDevice:
    """Resolve an LED Ball by its stable name and proxy commands to the BLE client."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        """Initialize the device wrapper."""
        self.hass = hass
        self.name = name
        self.device_id = _device_id_from_name(name)
        # A controller-class ball must not be the connected bridge (it would flood
        # the mesh), so its commands are routed through a device-class peer.
        self.needs_bridge = self.device_id != 0 and not _is_device_class(self.device_id)
        self._client: LightBall | None = None

    def _visible(self) -> dict[str, BLEDevice]:
        """Currently-visible LED balls, by stable name."""
        return {
            info.name: info.device
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
            if info.name and info.name.startswith(NAME_PREFIX)
        }

    @property
    def available(self) -> bool:
        """Whether this ball is currently visible to HA Bluetooth."""
        return self.name in self._visible()

    def _connection_target(self) -> tuple[BLEDevice, str] | None:
        """The (BLEDevice, name) to connect to in order to reach this ball.

        Device-class balls connect to themselves. A controller-class ball is reached
        only through a visible device-class peer; if none is visible we refuse rather
        than connect directly, because a direct connection to a controller-class ball
        makes it hijack the whole mesh.
        """
        visible = self._visible()
        if not self.needs_bridge:
            dev = visible.get(self.name)
            return (dev, self.name) if dev else None
        for peer_name, dev in visible.items():
            if peer_name != self.name and _is_device_class(_device_id_from_name(peer_name)):
                return (dev, peer_name)
        return None  # controller-class with no device-class peer: never connect directly

    def _client_for_current_device(self) -> LightBall:
        """Return a client bound to the right connection target for this ball."""
        target = self._connection_target()
        if target is None:
            raise LightBallNotFound(self.name)
        ble_device, conn_name = target
        if self._client is None:
            self._client = LightBall(ble_device, conn_name)
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
