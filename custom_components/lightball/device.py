"""BLE connection management for the LED Ball via HA Bluetooth (works through proxies)."""
from __future__ import annotations

import asyncio
import logging
import random

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from . import csrmesh
from .const import NAME_PREFIX, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


class LightBallDevice:
    """Resolves the ball's current address by stable name and sends commands.

    The ball uses a rotating private BLE address, so we never pin a MAC - we find
    the current advertisement matching the stable local name (e.g. LAB00001CEB11)
    via HA's Bluetooth manager, which transparently includes ESPHome BT proxies.
    """

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.hass = hass
        self.name = name                       # stable local name = unique id
        self._lock = asyncio.Lock()
        self._seq = random.randint(0x100000, 0xF00000)
        self._txn = 0
        self._source = random.randint(0x8001, 0xBFFE)

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFFFF
        return self._seq

    def _next_txn(self) -> int:
        self._txn = self._txn % 15 + 1
        return self._txn

    def _current_device(self) -> BLEDevice | None:
        """Find the BLEDevice currently advertising under our name (any address)."""
        for info in bluetooth.async_discovered_service_info(self.hass, connectable=True):
            if info.name == self.name or (
                info.name and info.name.upper().startswith(NAME_PREFIX)
                and SERVICE_UUID in [u.lower() for u in info.service_uuids]
                and info.name == self.name
            ):
                return info.device
        return None

    @property
    def available(self) -> bool:
        return self._current_device() is not None

    async def _send_payloads(self, payloads: list[bytes]) -> None:
        """Connect (through any adapter/proxy) and write each payload, split as needed."""
        ble_device = self._current_device()
        if ble_device is None:
            raise RuntimeError(f"{self.name} not currently visible to HA Bluetooth")
        async with self._lock:
            client = await establish_connection(
                BleakClientWithServiceCache, ble_device, self.name, max_attempts=4
            )
            try:
                for payload in payloads:
                    pkt = csrmesh.make_packet(payload, self._next_seq(), self._source)
                    for char_uuid, data in csrmesh.split_writes(pkt):
                        await client.write_gatt_char(char_uuid, data, response=False)
                    await asyncio.sleep(0.08)
            finally:
                await client.disconnect()

    # --- high-level commands ---------------------------------------------

    async def set_state(self, mode: int, color: int, level: int, *, turn_on: bool = True) -> None:
        """Select handshake -> (optional) ON -> commonMode(mode,color,level)."""
        payloads = [csrmesh.select_payload(self._next_txn()),
                    csrmesh.select_payload(self._next_txn())]
        if turn_on:
            payloads.append(csrmesh.power_payload(True, self._next_txn()))
        # send the command a couple of times (BLE is lossy)
        for _ in range(2):
            payloads.append(csrmesh.common_mode_payload(mode, color, level, self._next_txn()))
        await self._send_payloads(payloads)

    async def set_show(self, show_sel: int, *, turn_on: bool = True) -> None:
        """Activate an animated 'show' preset via showView (slot 1)."""
        payloads = [csrmesh.select_payload(self._next_txn()),
                    csrmesh.select_payload(self._next_txn())]
        if turn_on:
            payloads.append(csrmesh.power_payload(True, self._next_txn()))
        for _ in range(2):
            payloads.append(csrmesh.show_payload(show_sel, self._next_txn()))
        await self._send_payloads(payloads)

    async def turn_off(self) -> None:
        payloads = [csrmesh.select_payload(self._next_txn())]
        for _ in range(2):
            payloads.append(csrmesh.power_payload(False, self._next_txn()))
        await self._send_payloads(payloads)
