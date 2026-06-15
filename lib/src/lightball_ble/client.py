"""Async BLE client for the Holiday Show Home LED Ball.

Wraps connection management (via bleak-retry-connector) and the CSRmesh command
set. The caller owns device discovery and passes in a fresh ``BLEDevice`` (the ball
uses a rotating private address, so the address must be refreshed before each use).
"""

from __future__ import annotations

import asyncio
import logging
import random

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from . import protocol

_LOGGER = logging.getLogger(__name__)


class LightBall:
    """Connect to one LED Ball and send CSRmesh commands."""

    def __init__(self, ble_device: BLEDevice, name: str) -> None:
        self._ble_device = ble_device
        self._name = name
        self._lock = asyncio.Lock()
        self._seq = random.randint(0x100000, 0xF00000)
        self._txn = 0
        # A fresh random source per session avoids the mesh replay filter.
        self._source = random.randint(0x8001, 0xBFFE)

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Refresh the backing BLEDevice (its address rotates)."""
        self._ble_device = ble_device

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFFFF
        return self._seq

    def _next_txn(self) -> int:
        self._txn = self._txn % 15 + 1
        return self._txn

    async def _send(self, payloads: list[bytes]) -> None:
        async with self._lock:
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._name,
                max_attempts=4,
            )
            try:
                for payload in payloads:
                    packet = protocol.make_packet(
                        payload, self._next_seq(), self._source
                    )
                    for char_uuid, data in protocol.split_writes(packet):
                        await client.write_gatt_char(char_uuid, data, response=False)
                    await asyncio.sleep(0.08)
            finally:
                await client.disconnect()

    async def set_state(
        self,
        mode: int,
        color: int,
        level: int,
        *,
        turn_on: bool = True,
        dest: int = protocol.BROADCAST,
    ) -> None:
        """Select handshake -> (optional) power on -> commonMode(mode, color, level).

        ``dest`` addresses a single ball (0 = broadcast to all).
        """
        payloads = [
            protocol.select_payload(self._next_txn()),
            protocol.select_payload(self._next_txn()),
        ]
        if turn_on:
            payloads.append(protocol.power_payload(True, self._next_txn(), dest))
        for _ in range(2):  # BLE is lossy; send the command twice
            payloads.append(
                protocol.common_mode_payload(mode, color, level, self._next_txn(), dest)
            )
        await self._send(payloads)

    async def set_show(
        self, show_sel: int, *, turn_on: bool = True, dest: int = protocol.BROADCAST
    ) -> None:
        """Activate an animated 'show' preset via showView (slot 1)."""
        payloads = [
            protocol.select_payload(self._next_txn()),
            protocol.select_payload(self._next_txn()),
        ]
        if turn_on:
            payloads.append(protocol.power_payload(True, self._next_txn(), dest))
        for _ in range(2):
            payloads.append(protocol.show_payload(show_sel, self._next_txn(), dest=dest))
        await self._send(payloads)

    async def turn_off(self, *, dest: int = protocol.BROADCAST) -> None:
        """Turn the ball off."""
        payloads = [protocol.select_payload(self._next_txn())]
        for _ in range(2):
            payloads.append(protocol.power_payload(False, self._next_txn(), dest))
        await self._send(payloads)
