#!/usr/bin/env python3
"""Parse an Android btsnoop_hci.log, reassemble L2CAP/ATT, extract the ATT
writes/notifications, decrypt with our network key, and decode the commands the
official app sent. Handles ACL fragmentation (long packets split across frames).

Usage: parse_btsnoop.py <btsnoop_hci.log> [--all]
"""
import struct
import sys

import csrmesh_crypto as cm


def read_btsnoop(path):
    d = open(path, "rb").read()
    assert d[:8] == b"btsnoop\x00", "not a btsnoop file"
    off, out = 16, []
    while off + 24 <= len(d):
        ol, il, fl, dr, ts = struct.unpack(">IIIIq", d[off:off + 24])
        off += 24
        out.append((fl, d[off:off + il]))
        off += il
    return out


def att_pdus(recs):
    """Yield (direction, att_bytes) reassembling ACL L2CAP fragments per handle."""
    buf = {}   # handle -> (remaining_bytes, accumulated, direction)
    for fl, pkt in recs:
        if not pkt or pkt[0] != 0x02 or len(pkt) < 5:
            continue
        direction = "rx" if (fl & 0x1) else "tx"   # btsnoop flag bit0: 1=controller->host
        hf, acl_len = struct.unpack("<HH", pkt[1:3] + pkt[3:5])
        handle = hf & 0x0FFF
        pb = (hf >> 12) & 0x3
        data = pkt[5:5 + acl_len]
        if pb in (0x2, 0x0, 0x3):                  # start of a new L2CAP PDU
            if len(data) < 4:
                continue
            l2_len, cid = struct.unpack("<HH", data[:4])
            payload = data[4:]
            if len(payload) >= l2_len:
                yield direction, cid, payload[:l2_len]
            else:
                buf[handle] = (l2_len - len(payload), payload, cid, direction)
        elif pb == 0x1 and handle in buf:          # continuation
            rem, acc, cid, d = buf[handle]
            acc += data
            rem -= len(data)
            if rem <= 0:
                yield d, cid, acc
                del buf[handle]
            else:
                buf[handle] = (rem, acc, cid, d)


def decode(plain):
    if len(plain) < 3:
        return "(short) " + plain.hex()
    dest = int.from_bytes(plain[0:2], "little")
    op = plain[2]
    body = plain[3:]
    names = {0x89: "POWER", 0x8A: "LIGHT", 0x84: "ATTN", 0x83: "BATT",
             0x73: "DATA73", 0x70: "DATA70", 0x72: "DATA_RX", 0x77: "DATA77"}
    tag = names.get(op, f"op0x{op:02x}")
    extra = ""
    if op in (0x73, 0x70, 0x77) and len(body) >= 1:
        v = body
        if len(v) >= 4:
            extra = f"  vend[txn=0x{v[0]>>4:x} nib=0x{v[0]&0xf:x}] rest={v[1:].hex()}"
        else:
            extra = f"  vend={v.hex()}"
    return f"dst=0x{dest:04x} {tag} body={body.hex()}{extra}"


def main(path, show_all):
    recs = read_btsnoop(path)
    print(f"{len(recs)} HCI records")
    seen_seq = set()
    rows = []
    for direction, cid, att in att_pdus(recs):
        if cid != 0x0004 or not att:
            continue
        op = att[0]
        if op in (0x12, 0x52):
            kind, val = "WRITE", att[3:]
        elif op in (0x1b, 0x1d):
            kind, val = "NOTIFY", att[3:]
        else:
            continue
        if len(val) < 13:
            continue
        p = cm.parse_packet(bytes(val))
        if not p:
            continue
        seq, src, plain, ok = p
        key = (seq, src)
        if key in seen_seq:
            continue
        seen_seq.add(key)
        rows.append((kind, len(val), seq, src, plain))

    # group consecutive duplicate decoded-commands (ignoring txn nibble + seq)
    def sig(plain):
        if len(plain) >= 4 and plain[2] in (0x73, 0x70, 0x77):
            return (plain[0:2], plain[2], bytes([plain[3] & 0x0F]), plain[4:])
        return (plain,)

    print("\n=== decoded ATT writes/notifies (deduped consecutive) ===")
    last = None
    for kind, ln, seq, src, plain in rows:
        s = sig(plain)
        if not show_all and s == last and kind == "WRITE":
            continue
        last = s if kind == "WRITE" else last
        arrow = "APP->" if src == 0x8000 else f"0x{src:04x}->"
        print(f"[{kind:6} len={ln:2} {arrow}] {decode(plain)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    main(sys.argv[1], "--all" in sys.argv)
