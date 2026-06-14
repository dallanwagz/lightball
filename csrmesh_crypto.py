"""
CSRmesh MTL crypto + packet framing for the Holiday Showtime / Showhome bulbs.

Ported directly from the decompiled `com.holidayshow` v0.46 app (the authoritative
source for *our* hardware), and cross-checked against the public `csrmesh` library
(github.com/nkaminski/csrmesh). The two agree byte-for-byte, which is a good sign.

Key facts established from the decompiled source (see SURVEY.md for file:line refs):

  * Network passphrase is hardcoded "686868"  (CenterActivity.java:244).
  * Network key  = reverse( SHA-256(passphrase + b"\\x00MCP") )[:16]
                 = reverse( SHA-256(...)[16:32] )            (as.java:246 + bg.a reverse)
                 = 6750aae5bf990f0c660e5ed351a8cd26
  * Payload cipher (c.java): AES-128 over a 16-byte counter block, XOR keystream.
        counter block = seq(3 LE) | 0x00 | source(2 LE) | networkIV(8=zero) | 0x00 0x00
    For payloads <= 16 bytes this is identical to AES-OFB/CTR with one block.
  * MIC (as.java HMAC helper): reverse( HMAC-SHA256(key, b"\\x00"*8 | seq(3) | source(2)
        | enc_payload) )[:8].
  * Wire packet = seq(3 LE) | source(2 LE) | enc_payload | MIC(8) | 0xFF
  * The destination device id (0x0000 = broadcast) is the first 2 bytes of the
    *encrypted* payload; source defaults to 0x8000 (aj.i = Short.MIN_VALUE).

Model message layouts (aj.java:280-283, av.java, ah.java):
  Power  model opcode 0x89:  setState unack  -> [0x89, 0x00, state]
                             setState ack    -> [0x89, 0x01, state, txn]
                             (state: 0=off 1=on 2=standby 3=onstandby; PowerState ordinal)
  Light  model opcode 0x8A:  setLevel unack  -> [0x8A, 0x00, level]
                             setRgb   unack  -> [0x8A, 0x02, R, G, B, level, durLo, durHi]
"""

import hashlib
import hmac
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_PASSPHRASE = b"686868"
DEFAULT_SOURCE = 0x8000          # aj.i default (Short.MIN_VALUE), the controller address
BROADCAST = 0x0000               # device id 0 = all devices on the mesh

# PowerState ordinals (com.csr.csrmesh2.PowerState)
POWER_OFF = 0
POWER_ON = 1
POWER_STANDBY = 2
POWER_ON_FROM_STANDBY = 3


def derive_key(passphrase: bytes = DEFAULT_PASSPHRASE) -> bytes:
    """reverse(SHA-256(passphrase + b'\\x00MCP'))[:16]  -- matches as.java + bg.a()."""
    digest = hashlib.sha256(passphrase + b"\x00MCP").digest()
    return bytes(reversed(digest))[:16]


DEFAULT_KEY = derive_key()


def _aes_ecb_block(key: bytes, block16: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return enc.update(block16) + enc.finalize()


def make_packet(payload: bytes, seq: int, *, key: bytes = DEFAULT_KEY,
                source: int = DEFAULT_SOURCE) -> bytes:
    """Frame + encrypt one MTL packet. `payload` = dest(2 LE) + model message bytes."""
    if not 0 <= seq <= 0xFFFFFF:
        raise ValueError("seq must be a 24-bit value")
    if len(payload) > 16:
        # c.java XORs against a single 16-byte AES block; longer payloads need the
        # app's two-control-point split which we have not implemented yet.
        raise ValueError("payload >16 bytes needs MTL continuation (not implemented)")

    seq3 = struct.pack("<I", seq)[:3]
    src2 = struct.pack("<H", source & 0xFFFF)

    counter = seq3 + b"\x00" + src2 + b"\x00" * 10          # networkIV = zero
    keystream = _aes_ecb_block(key, counter)
    enc = bytes(p ^ k for p, k in zip(payload, keystream))

    prehmac = b"\x00" * 8 + seq3 + src2 + enc
    mic = bytes(reversed(hmac.new(key, prehmac, hashlib.sha256).digest()))[:8]

    return seq3 + src2 + enc + mic + b"\xff"


# --- model message helpers --------------------------------------------------

def _payload(dest: int, *msg: int) -> bytes:
    return struct.pack("<H", dest & 0xFFFF) + bytes(msg)


def power(state: int, dest: int = BROADCAST) -> bytes:
    """Power model setState, unacknowledged (av.java z=false)."""
    return _payload(dest, 0x89, 0x00, state & 0xFF)


def set_level(level: int, dest: int = BROADCAST) -> bytes:
    """Light model setLevel (brightness 0-255), unacknowledged (ah.java)."""
    return _payload(dest, 0x8A, 0x00, level & 0xFF)


def set_power_level(power: int, level: int, dest: int = BROADCAST, duration_ms: int = 0,
                    sustain_ms: int = 0, decay_ms: int = 0) -> bytes:
    """Light model setPowerLevel, unacknowledged (ah.java sub 0x04): set power state
    AND brightness in one message (the 'turn on to this level' command)."""
    return _payload(dest, 0x8A, 0x04, power & 0xFF, level & 0xFF,
                    duration_ms & 0xFF, (duration_ms >> 8) & 0xFF,
                    sustain_ms & 0xFF, (sustain_ms >> 8) & 0xFF,
                    decay_ms & 0xFF, (decay_ms >> 8) & 0xFF)


def set_rgb(r: int, g: int, b: int, level: int = 0xFF, duration_ms: int = 0,
            dest: int = BROADCAST) -> bytes:
    """Light model setRgb, unacknowledged (ah.java). NOTE: 10-byte payload -> 24-byte
    wire packet; needs an MTU >= 27 or the not-yet-implemented control-point split."""
    return _payload(dest, 0x8A, 0x02, r & 0xFF, g & 0xFF, b & 0xFF, level & 0xFF,
                    duration_ms & 0xFF, (duration_ms >> 8) & 0xFF)


# --- vendor DataModel commands (Holiday Showhome effect engine) --------------
# These are the commands the app actually uses to drive the bulbs' firmware
# effect modes. Sent as a CSRmesh DataModel "data block" (opcode 0x73 unack,
# u.java) carrying a 10-byte vendor payload (Commands.java). The standard Light
# model only paints one frame; the firmware effect repaints over it, so to make
# anything *stick* you must change the mode here.
#
# 10-byte vendor payload layout (Commands.java):
#   [0] = (txn<<4) | 0x03         txn = rolling 1..15 transaction nibble
#   [1] = batchId                 (0 = all)
#   [2] = typeId hi, [3] = typeId lo   (0xFFFF = all device types; app broadcast)
#   [4] = (txn<<4) | cmd          cmd nibble: 0x3 commondMode, 0xA showView, 0xC customSet
#   [5..7] = command params
#   [8],[9] = password CRC (0,0 when no password is set)

DATA_OPCODE_UNACK = 0x73
TYPE_ALL = 0xFFFF
TYPE_SHOW = 0xFFFE      # typeId the app uses for showView/custom broadcast


def data_block(vendor: bytes, dest: int = BROADCAST) -> bytes:
    """Wrap a 10-byte vendor payload as a DataModel block payload (pre-framing)."""
    if len(vendor) > 10:
        raise ValueError("vendor payload max 10 bytes")
    return _payload(dest, DATA_OPCODE_UNACK, *vendor)


def _vendor(txn: int, batch: int, typeid: int, cmd: int, b5: int, b6: int, b7: int) -> bytes:
    f = (txn & 0x0F) << 4
    return bytes([f | 0x3, batch & 0xFF, (typeid >> 8) & 0xFF, typeid & 0xFF,
                  f | (cmd & 0x0F), b5 & 0xFF, b6 & 0xFF, b7 & 0xFF, 0x00, 0x00])


def commond_mode(mode: int, color: int, speed: int = 0, *, txn: int = 1,
                 batch: int = 0, typeid: int = TYPE_ALL) -> bytes:
    """commondMode: set firmware effect mode. mode 0 = Steady/solid. color is a
    palette index; speed encoded as (4-speed). (Commands.java:71, BLEMainActivity:236)"""
    return _vendor(txn, batch, typeid, 0x3, mode, color, (4 - speed) & 0xFF)


def show_view(mode: int, color: int, *, txn: int = 1, batch: int = 0,
              typeid: int = TYPE_SHOW) -> bytes:
    """showView: select a 'show' display mode. (Commands.java:119, BLEMainActivity:260)"""
    return _vendor(txn, batch, typeid, 0xA, mode, color, 0)


# --- acknowledged queries + reply parsing (for confirming comms) ------------

def power_get_state(dest: int = BROADCAST, ackid: int = 1) -> bytes:
    """Power model getState (acknowledged). Bulb should reply MESSAGE_POWER_STATE.
    (av.java a(int)). """
    return _payload(dest, 0x89, 0x04, ackid & 0xFF)


def light_get_state(dest: int = BROADCAST, ackid: int = 1) -> bytes:
    """Light model getState (acknowledged). (ah.java)."""
    return _payload(dest, 0x8A, 0x07, ackid & 0xFF)


def battery_get_state(dest: int = BROADCAST, ackid: int = 1) -> bytes:
    """Battery model getState (acknowledged). opcode 0x83 (jaj.java:289)."""
    return _payload(dest, 0x83, 0x00, ackid & 0xFF)


def attention(on: bool = True, duration_ms: int = 0xFFFF, dest: int = BROADCAST,
              txn: int = 1) -> bytes:
    """Attention model setState (f.java, opcode 0x84): make the device attract
    attention. Empirically this HALTS the firmware animation and holds steady."""
    return _payload(dest, 0x84, 0x00, 1 if on else 0,
                    duration_ms & 0xFF, (duration_ms >> 8) & 0xFF, txn & 0xFF)


def query_status(*, txn: int = 1, batch: int = 0, typeid: int = TYPE_ALL) -> bytes:
    """Vendor queryStatus (Commands.java:59) - should elicit a DataModel reply if the
    vendor path + password are accepted. cmd nibble 0x2."""
    return _vendor(txn, batch, typeid, 0x2, 0, 0, 0)


def select(*, txn: int = 1, batch: int = 0, typeid: int = TYPE_ALL) -> bytes:
    """sendSelect (Commands.java:163) - the device "select" handshake the app sends
    (and repeats) so devices accept subsequent commands. Distinct layout: byte0's low
    nibble is 0xE and there is NO second command byte.
        [txn|0xE, batch, typeIdHi, typeIdLo, 0, 0, 0, 0, 0, 0]
    The app calls sendSelect(0, 0, 0xFFFF)."""
    f = (txn & 0x0F) << 4
    return bytes([f | 0xE, batch & 0xFF, (typeid >> 8) & 0xFF, typeid & 0xFF,
                  0, 0, 0, 0, 0, 0])


def parse_packet(pkt: bytes, key: bytes = DEFAULT_KEY):
    """Decrypt a received MTL packet -> (seq, source, plaintext_payload, mic_ok).
    plaintext_payload = dest(2 LE) + opcode + params. Inverse of make_packet."""
    data = pkt
    # strip trailing 0xFF EOF if the framing includes one
    if len(data) >= 14 and data[-1] == 0xFF:
        data = data[:-1]
    if len(data) < 13:
        return None
    seq3, src2, mic = data[0:3], data[3:5], data[-8:]
    enc = data[5:-8]
    counter = seq3 + b"\x00" + src2 + b"\x00" * 10
    keystream = _aes_ecb_block(key, counter)
    plain = bytes(p ^ k for p, k in zip(enc, keystream))
    prehmac = b"\x00" * 8 + seq3 + src2 + enc
    exp = bytes(reversed(hmac.new(key, prehmac, hashlib.sha256).digest()))[:8]
    return (int.from_bytes(seq3, "little"), int.from_bytes(src2, "little"),
            plain, exp == mic)


if __name__ == "__main__":
    # offline self-test: print the key and a couple of framed packets
    print("network key :", DEFAULT_KEY.hex())
    assert DEFAULT_KEY.hex() == "6750aae5bf990f0c660e5ed351a8cd26", "key mismatch!"
    print("power ON    :", make_packet(power(POWER_ON), seq=0x000001).hex())
    print("power OFF   :", make_packet(power(POWER_OFF), seq=0x000002).hex())
    print("level 128   :", make_packet(set_level(128), seq=0x000003).hex())
    print("rgb red     :", make_packet(set_rgb(255, 0, 0), seq=0x000004).hex(),
          "(24B - may need MTU split)")
    print("self-test OK")
