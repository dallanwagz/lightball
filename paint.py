#!/usr/bin/env python3
"""Hold an exact RGB color by streaming setRgb at max rate, trying to out-pace the
firmware effect. Usage: paint.py R G B [seconds]"""
import asyncio
import random
import sys
import time

from bleak import BleakClient

import csrmesh_crypto as cm
from lightball import find_device, pick_chars, next_seq


async def main(r, g, b, seconds):
    dev = await find_device("LA", None)
    if not dev:
        print("no bulb found"); return 1
    src = random.randint(0x8001, 0xBFFF)
    async with BleakClient(dev) as client:
        _, wc, _ = pick_chars(client)
        no_resp = "write-without-response" in wc.properties
        print(f"connected; write -> {wc.uuid}; src=0x{src:04x}; "
              f"streaming rgb({r},{g},{b}) at max rate for {seconds}s")
        end = time.monotonic() + seconds
        n = 0
        while time.monotonic() < end:
            pkt = cm.make_packet(cm.set_rgb(r, g, b), next_seq(), source=src)
            await client.write_gatt_char(wc, pkt, response=not no_resp)
            n += 1
            await asyncio.sleep(0.03)        # ~33 Hz, a realistic on-air rate
        print(f"done; sent {n} frames (~{n/seconds:.0f}/s)")
    return 0


if __name__ == "__main__":
    r, g, b = (int(x) for x in sys.argv[1:4])
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else 15.0
    sys.exit(asyncio.run(main(r, g, b, secs)))
