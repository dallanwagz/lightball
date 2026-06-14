#!/usr/bin/env python3
"""Definitive comms test: subscribe to notifications, send acknowledged queries to
the bulb, and decrypt any replies. A reply that decrypts with a valid MIC proves our
packets reach the bulb and the key/crypto are correct - independent of any light show.

Usage: probe.py [device_id_hex]    (default: broadcast 0x0000, then unicast 0xEB11)
"""
import asyncio
import random
import sys

from bleak import BleakClient

import csrmesh_crypto as cm
from lightball import SERVICE, find_device, next_seq, pick_chars


async def main(dest):
    dev = await find_device("LA", None)
    if not dev:
        print("no bulb found"); return 1
    src = random.randint(0x8001, 0xBFFF)
    got = []

    async with BleakClient(dev) as client:
        svc, write_char, _retry = pick_chars(client)
        # subscribe to every notify/indicate characteristic in the mesh service
        notif_chars = [c for c in svc.characteristics
                       if "notify" in c.properties or "indicate" in c.properties]

        def mk_cb(uuid):
            def cb(_, data):
                parsed = cm.parse_packet(bytes(data))
                tag = ""
                if parsed:
                    seq, psrc, plain, ok = parsed
                    tag = (f"  -> DECRYPT seq=0x{seq:06x} src=0x{psrc:04x} mic={'OK' if ok else 'BAD'}"
                           f" payload={plain.hex()}")
                print(f"notify [{uuid[-12:]}]: {bytes(data).hex()}{tag}")
                got.append(bytes(data))
            return cb

        for c in notif_chars:
            try:
                await client.start_notify(c, mk_cb(c.uuid))
                print(f"subscribed notify: {c.uuid} ({','.join(c.properties)})")
            except Exception as e:  # noqa: BLE001
                print(f"subscribe failed {c.uuid}: {e}")
        no_resp = "write-without-response" in write_char.properties
        print(f"write -> {write_char.uuid}  src=0x{src:04x}\n")

        async def tx(label, payload):
            pkt = cm.make_packet(payload, next_seq(), source=src)
            await client.write_gatt_char(write_char, pkt, response=not no_resp)
            print(f"sent {label}: {pkt.hex()}")

        queries = [
            ("power_get_state", cm.power_get_state(dest)),
            ("light_get_state", cm.light_get_state(dest)),
            ("battery_get_state", cm.battery_get_state(dest)),
        ]
        for label, payload in queries:
            for ackid in range(2):           # a couple tries, mesh is lossy
                await tx(f"{label}#{ackid}", payload)
                await asyncio.sleep(0.4)
            await asyncio.sleep(0.8)

        print("\nlistening 4s for late replies...")
        await asyncio.sleep(4.0)

    print(f"\n=== {len(got)} notification(s) received ===")
    return 0


if __name__ == "__main__":
    dest = int(sys.argv[1], 16) if len(sys.argv) > 1 else cm.BROADCAST
    print(f"probing dest=0x{dest:04x}")
    sys.exit(asyncio.run(main(dest)))
