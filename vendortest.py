#!/usr/bin/env python3
"""Test whether the vendor DataModel (effect-engine) path is accepted, using the
reply channel. Sends vendor queryStatus + a couple of mode commands to the bulb and
prints all decrypted replies. Compares against standard-model getState as a control.

Usage: vendortest.py [device_id_hex]   (default 0xEB11, the bulb)
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
    replies = []

    async with BleakClient(dev) as client:
        svc, write_char, _ = pick_chars(client)
        notif_chars = [c for c in svc.characteristics if "notify" in c.properties]

        def cb(_, data):
            b = bytes(data)
            p = cm.parse_packet(b)
            if p:
                seq, psrc, plain, ok = p
                # only show packets FROM the bulb (not our own echoes)
                if psrc == dest or psrc == 0xEB11:
                    print(f"  REPLY src=0x{psrc:04x} payload={plain.hex()}")
                    replies.append((psrc, plain))

        for c in notif_chars:
            await client.start_notify(c, cb)
        no_resp = "write-without-response" in write_char.properties
        print(f"write -> {write_char.uuid}  dest=0x{dest:04x}  src=0x{src:04x}\n")

        async def tx(label, payload, n=3):
            print(f"--- {label} ---")
            for i in range(n):
                pkt = cm.make_packet(payload, next_seq(), source=src)
                await client.write_gatt_char(write_char, pkt, response=not no_resp)
                await asyncio.sleep(0.35)
            await asyncio.sleep(0.8)

        # control: standard-model getState (we KNOW this replies)
        await tx("light_get_state (control)", cm.light_get_state(dest))
        # vendor path tests
        await tx("vendor queryStatus typeid=FFFF",
                 cm.data_block(cm.query_status(typeid=0xFFFF), dest))
        await tx("vendor queryStatus typeid=0000",
                 cm.data_block(cm.query_status(typeid=0x0000), dest))
        await tx("vendor commondMode solid typeid=FFFF",
                 cm.data_block(cm.commond_mode(0, 1, 0, typeid=0xFFFF), dest))
        print("\nlistening 3s...")
        await asyncio.sleep(3.0)

    print(f"\n=== {len(replies)} bulb reply/replies captured ===")
    return 0


if __name__ == "__main__":
    dest = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0xEB11
    sys.exit(asyncio.run(main(dest)))
