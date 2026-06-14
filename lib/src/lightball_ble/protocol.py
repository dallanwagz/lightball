"""CSRmesh MTL crypto and command builders for the LED Ball.

Self-contained reimplementation of the framing the official "Show Home" app sends:
an AES-128 counter-mode payload, a byte-reversed truncated HMAC-SHA256 MIC, and a
trailing 0xFF, split across two GATT control-point characteristics for packets
longer than 20 bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# GATT bridge service and the two MTL control-point characteristics.
SERVICE_UUID = "0000fef1-0000-1000-8000-00805f9b34fb"
CP1_UUID = "c4edc000-9daf-11e3-8003-00025b000b00"  # first 20 bytes of a packet
CP2_UUID = "c4edc000-9daf-11e3-8004-00025b000b00"  # remainder

PASSPHRASE = b"686868"
TYPEID = 0xFFFF  # product bitmask the app uses for the ball (all products)

MODE_CLOSE = 0
MODE_STEADY = 1
MODE_ON = 255

BROADCAST = 0x0000
DEFAULT_SOURCE = 0x8000


def derive_key(passphrase: bytes = PASSPHRASE) -> bytes:
    """Network key = reverse(SHA-256(passphrase + b"\\x00MCP"))[:16]."""
    return bytes(reversed(hashlib.sha256(passphrase + b"\x00MCP").digest()))[:16]


KEY = derive_key()


def _aes_block(block16: bytes) -> bytes:
    enc = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    return enc.update(block16) + enc.finalize()


def make_packet(payload: bytes, seq: int, source: int = DEFAULT_SOURCE) -> bytes:
    """Frame and encrypt one MTL packet (payload = dest(2 LE) + message bytes)."""
    seq3 = struct.pack("<I", seq & 0xFFFFFF)[:3]
    src2 = struct.pack("<H", source & 0xFFFF)
    counter = seq3 + b"\x00" + src2 + b"\x00" * 10
    keystream = _aes_block(counter)
    enc = bytes(p ^ k for p, k in zip(payload, keystream, strict=False))
    mic = bytes(
        reversed(
            hmac.new(KEY, b"\x00" * 8 + seq3 + src2 + enc, hashlib.sha256).digest()
        )
    )[:8]
    return seq3 + src2 + enc + mic + b"\xff"


def _data_block(vendor: bytes, dest: int = BROADCAST) -> bytes:
    return struct.pack("<H", dest & 0xFFFF) + bytes([0x73]) + vendor


def _vendor(
    txn: int, cmd: int, b5: int, b6: int, b7: int, typeid: int = TYPEID
) -> bytes:
    f = (txn & 0x0F) << 4
    return bytes(
        [
            f | 0x3,
            0x00,
            (typeid >> 8) & 0xFF,
            typeid & 0xFF,
            f | (cmd & 0x0F),
            b5 & 0xFF,
            b6 & 0xFF,
            b7 & 0xFF,
            0x00,
            0x00,
        ]
    )


def select_payload(txn: int) -> bytes:
    """sendSelect handshake: [txn|0xE, 0, FF, FF, 0x6]."""
    f = (txn & 0x0F) << 4
    return _data_block(bytes([f | 0xE, 0x00, 0xFF, 0xFF, 0, 0, 0, 0, 0, 0]))


def common_mode_payload(mode: int, color: int, level: int, txn: int) -> bytes:
    """commonMode(mode, color, brightness level 0-4); wire byte = 4 - level."""
    return _data_block(_vendor(txn, 0x3, mode, color, (4 - level) & 0xFF))


def power_payload(on: bool, txn: int) -> bytes:
    """commonMode power toggle (mode 255 = on, 0 = off)."""
    return _data_block(_vendor(txn, 0x3, MODE_ON if on else MODE_CLOSE, 0, 0))


def show_payload(show_sel: int, txn: int, slot: int = 1) -> bytes:
    """showView (animated preset): cmd nibble 0xA, byte5=slot(1-3), byte6=show index."""
    f = (txn & 0x0F) << 4
    v = bytes(
        [
            f | 0x3,
            0x00,
            (TYPEID >> 8) & 0xFF,
            TYPEID & 0xFF,
            f | 0xA,
            slot & 0xFF,
            show_sel & 0xFF,
            0,
            0,
            0,
        ]
    )
    return _data_block(v)


def split_writes(packet: bytes) -> list[tuple[str, bytes]]:
    """GATT writes for a packet: >20 bytes splits across CP1 then CP2."""
    if len(packet) > 20:
        return [(CP1_UUID, packet[:20]), (CP2_UUID, packet[20:])]
    return [(CP1_UUID, packet)]
