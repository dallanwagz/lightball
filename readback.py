#!/usr/bin/env python3
"""Eyes-free control test: read the bulb's light state, send a sequence of standard-
model commands (power on, level up, set color, setPowerLevel), and read the state
back to see which commands the bulb actually accepts/reflects."""
import asyncio
import random
import sys

from bleak import BleakClient

import csrmesh_crypto as cm
from lightball import find_device, next_seq, pick_chars

DEST = 0xEB11


def decode_light(plain):
    # payload: dest(2) opcode(0x8a) sub(0x08) power level R G B ...
    if len(plain) >= 4 and plain[2] == 0x8A and plain[3] == 0x08:
        f = plain[4:]
        fields = {"power": f[0] if len(f) > 0 else None,
                  "level": f[1] if len(f) > 1 else None,
                  "R": f[2] if len(f) > 2 else None,
                  "G": f[3] if len(f) > 3 else None,
                  "B": f[4] if len(f) > 4 else None}
        return fields
    return None


async def main():
    dev = await find_device("LA", None)
    if not dev:
        print("no bulb found"); return 1
    src = random.randint(0x8001, 0xBFFF)
    last = {}

    async with BleakClient(dev) as client:
        svc, wc, _ = pick_chars(client)
        no_resp = "write-without-response" in wc.properties

        def cb(_, data):
            p = cm.parse_packet(bytes(data))
            if p and p[1] == DEST:
                d = decode_light(p[2])
                if d:
                    last["state"] = d
                    last["raw"] = p[2].hex()

        for c in [c for c in svc.characteristics if "notify" in c.properties]:
            await client.start_notify(c, cb)

        async def tx(payload, n=2):
            for _ in range(n):
                await client.write_gatt_char(wc, cm.make_packet(payload, next_seq(),
                                              source=src), response=not no_resp)
                await asyncio.sleep(0.25)

        async def query(label):
            last.pop("state", None)
            await tx(cm.light_get_state(DEST), n=3)
            await asyncio.sleep(0.8)
            print(f"{label:32} -> {last.get('state')}  raw={last.get('raw')}")

        print(f"dest=0x{DEST:04x} src=0x{src:04x}\n")
        await query("baseline")
        await tx(cm.power(cm.POWER_ON, DEST));        await query("after power ON")
        await tx(cm.set_level(255, DEST));            await query("after set_level 255")
        await tx(cm.set_rgb(0, 255, 0, dest=DEST));   await query("after setRgb green")
        await tx(cm.set_power_level(1, 255, DEST));   await query("after setPowerLevel on/255")
        await tx(cm.set_rgb(0, 0, 255, dest=DEST));   await query("after setRgb blue")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
