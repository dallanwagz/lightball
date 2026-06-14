"""Base entity for the Holiday Show Home LED Ball."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .device import LightBallDevice

if TYPE_CHECKING:
    from . import LightBallConfigEntry


class LightBallEntity(Entity):
    """Common base for LED Ball entities."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, device: LightBallDevice, entry: LightBallConfigEntry) -> None:
        """Initialize the entity."""
        self._device = device
        assert entry.unique_id is not None
        self._attr_unique_id = entry.unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="Willis Electric / Kupoint",
            model="Show Home App Light Ball (AL96, CSRmesh)",
        )

    @property
    def available(self) -> bool:
        """Return whether the ball is currently visible to HA Bluetooth."""
        return self._device.available

    async def async_added_to_hass(self) -> None:
        """Push state when the ball's advertisement is seen (presence changes)."""
        await super().async_added_to_hass()
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_bluetooth_event,
                BluetoothCallbackMatcher(local_name=self._device.name),
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )

    @callback
    def _async_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a fresh advertisement for this ball."""
        self.async_write_ha_state()
