"""CSRmesh MTL crypto + command builders for the LED Ball (HA integration copy).

Self-contained; see the project SURVEY.md for how this was reverse-engineered. Builds
the exact encrypted packets the official app sends, including the two-control-point
split. Uses `cryptography` (pulled in by HA's deps) for AES.
"""
from __future__ import annotations

import hashlib
import hmac
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import CP1_UUID, CP2_UUID, MODE_CLOSE, MODE_ON, MODE_STEADY, PASSPHRASE, TYPEID

BROADCAST = 0x0000
DEFAULT_SOURCE = 0x8000


def _derive_key(passphrase: bytes) -> bytes:
    return bytes(reversed(hashlib.sha256(passphrase + b"\x00MCP").digest()))[:16]


KEY = _derive_key(PASSPHRASE)


def _aes_block(block16: bytes) -> bytes:
    enc = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    return enc.update(block16) + enc.finalize()


def make_packet(payload: bytes, seq: int, source: int = DEFAULT_SOURCE) -> bytes:
    """Frame + encrypt one MTL packet (payload = dest(2 LE) + message bytes)."""
    seq3 = struct.pack("<I", seq & 0xFFFFFF)[:3]
    src2 = struct.pack("<H", source & 0xFFFF)
    counter = seq3 + b"\x00" + src2 + b"\x00" * 10
    ks = _aes_block(counter)
    enc = bytes(p ^ k for p, k in zip(payload, ks))
    mic = bytes(reversed(hmac.new(KEY, b"\x00" * 8 + seq3 + src2 + enc, hashlib.sha256).digest()))[:8]
    return seq3 + src2 + enc + mic + b"\xff"


def _data_block(vendor: bytes, dest: int = BROADCAST) -> bytes:
    return struct.pack("<H", dest & 0xFFFF) + bytes([0x73]) + vendor


def _vendor(txn: int, cmd: int, b5: int, b6: int, b7: int, typeid: int = TYPEID) -> bytes:
    f = (txn & 0x0F) << 4
    return bytes([f | 0x3, 0x00, (typeid >> 8) & 0xFF, typeid & 0xFF,
                  f | (cmd & 0x0F), b5 & 0xFF, b6 & 0xFF, b7 & 0xFF, 0x00, 0x00])


def select_payload(txn: int) -> bytes:
    """sendSelect handshake: [txn|0xE, 0, FF, FF, 0x6]."""
    f = (txn & 0x0F) << 4
    return _data_block(bytes([f | 0xE, 0x00, 0xFF, 0xFF, 0, 0, 0, 0, 0, 0]))


def common_mode_payload(mode: int, color: int, level: int, txn: int) -> bytes:
    """commonMode(mode, color, brightness level 0-4) -> wire byte 4-level."""
    return _data_block(_vendor(txn, 0x3, mode, color, (4 - level) & 0xFF))


def power_payload(on: bool, txn: int) -> bytes:
    return _data_block(_vendor(txn, 0x3, MODE_ON if on else MODE_CLOSE, 0, 0))


def split_writes(packet: bytes) -> list[tuple[str, bytes]]:
    """Return the GATT writes for a packet: >20 bytes splits across CP1 then CP2."""
    if len(packet) > 20:
        return [(CP1_UUID, packet[:20]), (CP2_UUID, packet[20:])]
    return [(CP1_UUID, packet)]
