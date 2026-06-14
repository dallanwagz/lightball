"""Tests for the LightBall BLE client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from lightball_ble.client import LightBall
from lightball_ble.protocol import CP1_UUID


async def _run(method: str, *args) -> MagicMock:
    """Drive one client method with a mocked BLE connection; return the gatt client."""
    gatt = MagicMock()
    gatt.write_gatt_char = AsyncMock()
    gatt.disconnect = AsyncMock()
    with patch(
        "lightball_ble.client.establish_connection", AsyncMock(return_value=gatt)
    ):
        ball = LightBall(MagicMock(), "LAB00001CEB11")
        await getattr(ball, method)(*args)
    return gatt


async def test_set_state_connects_writes_and_disconnects() -> None:
    """set_state opens a connection, writes packets, and always disconnects."""
    gatt = await _run("set_state", 1, 0, 2)
    assert gatt.write_gatt_char.await_count >= 1
    # The first GATT write of any packet goes to the primary control point.
    assert gatt.write_gatt_char.await_args_list[0].args[0] == CP1_UUID
    gatt.disconnect.assert_awaited_once()


async def test_set_show_writes() -> None:
    """set_show writes at least one packet and disconnects."""
    gatt = await _run("set_show", 6)
    assert gatt.write_gatt_char.await_count >= 1
    gatt.disconnect.assert_awaited_once()


async def test_turn_off_writes() -> None:
    """turn_off writes at least one packet and disconnects."""
    gatt = await _run("turn_off")
    assert gatt.write_gatt_char.await_count >= 1
    gatt.disconnect.assert_awaited_once()


async def test_set_ble_device_updates_target() -> None:
    """Refreshing the BLEDevice swaps the target used for the next connection."""
    ball = LightBall(MagicMock(), "LAB00001CEB11")
    new_device = MagicMock()
    ball.set_ble_device(new_device)
    assert ball._ble_device is new_device
