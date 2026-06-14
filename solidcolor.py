#!/usr/bin/env python3
"""Hold an exact solid color: stream Attention (which halts the firmware animation)
together with setPowerLevel + setRgb to set the actual color.
Usage: solidcolor.py R G B [seconds]"""
import asyncio
import random
import sys
import time

from bleak import BleakClient

import csrmesh_crypto as cm
from lightball import find_device, next_seq, pick_chars

DEST = 0xEB11


async def main(r, g, b, seconds):
    dev = await find_device("LA", None)
    if not dev:
        print("no bulb found"); return 1
    src = random.randint(0x8001, 0xBFFF)
    async with BleakClient(dev) as client:
        _, wc, _ = pick_chars(client)
        no_resp = "write-without-response" in wc.properties
        print(f"connected; src=0x{src:04x}; holding rgb({r},{g},{b}) for {seconds}s")

        async def tx(payload):
            await client.write_gatt_char(wc, cm.make_packet(payload, next_seq(),
                                          source=src), response=not no_resp)

        txn = 1
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            await tx(cm.attention(True, 0xFFFF, DEST, txn))   # halt animation
            await tx(cm.set_power_level(1, 255, DEST))        # base on, full
            await tx(cm.set_rgb(r, g, b, dest=DEST))          # set color
            txn = txn % 15 + 1
            await asyncio.sleep(0.08)
        print("done")
    return 0


if __name__ == "__main__":
    r, g, b = (int(x) for x in sys.argv[1:4])
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else 15.0
    sys.exit(asyncio.run(main(r, g, b, secs)))
