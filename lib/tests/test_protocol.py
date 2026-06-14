"""Tests for the CSRmesh protocol builders."""

from __future__ import annotations

from lightball_ble import derive_key, make_packet, protocol


def test_network_key_matches_hardware() -> None:
    """The derived key matches the value verified against real devices."""
    assert derive_key().hex() == "6750aae5bf990f0c660e5ed351a8cd26"


def test_show_payload_multicolor_bytes() -> None:
    """MultiColor (show 6, txn 8) matches the bytes captured from the app."""
    assert protocol.show_payload(6, 8).hex() == "0000738300ffff8a0106000000"


def test_common_mode_brightness_is_inverted() -> None:
    """Brightness is sent as 4 - level on the wire."""
    payload = protocol.common_mode_payload(1, 0, 2, 1)
    # vendor byte 7 (index 3+7 = 10) carries 4 - level.
    assert payload[3 + 7] == 4 - 2


def test_split_writes_short_packet_single_write() -> None:
    """A <=20 byte packet uses only the first control point."""
    short = b"\x00" * 10
    assert protocol.split_writes(short) == [(protocol.CP1_UUID, short)]


def test_split_writes_long_packet_two_control_points() -> None:
    """A >20 byte packet splits 20 bytes to CP1 then the remainder to CP2."""
    packet = bytes(range(25))
    writes = protocol.split_writes(packet)
    assert writes[0][0] == protocol.CP1_UUID
    assert len(writes[0][1]) == 20
    assert writes[1][0] == protocol.CP2_UUID
    assert writes[1][1] == bytes(range(20, 25))


def test_make_packet_framing() -> None:
    """A framed packet carries the seq/source header and a 0xFF terminator."""
    packet = make_packet(b"\x00\x00\x73\x01", seq=0x123456, source=0x8001)
    assert packet[:3] == b"\x56\x34\x12"  # seq, little-endian 3 bytes
    assert packet[3:5] == b"\x01\x80"  # source, little-endian
    assert packet[-1] == 0xFF
