#!/usr/bin/env python3
"""Hold the ball on a steady solid color the way the app does: persistent connection,
source 0x8000, streaming the steady command + heartbeat polls continuously.
Usage: hold.py <color> [seconds]   (color = palette index, e.g. 12)"""
import asyncio
import sys

from bleak import BleakClient

import csrmesh_crypto as cm
from lightball import find_device, next_seq, pick_chars

DEST = 0xEB11      # unicast to the ball so it commits (not just relays a broadcast)
SRC = 0x8000
TYPEID = 0xFC7B


def steady(color, txn):
    # commondMode mode=2 (Steady), color, speed byte 0x02 -> vendor exactly like the app
    return cm.data_block(cm.commond_mode(2, color, 2, txn=txn, typeid=TYPEID), DEST)


def heartbeat_select(txn):
    # sendSelect: nibble 0xE, typeId 0xFFFF, params 0  (Commands.java sendSelect)
    v = cm._vendor(txn, 0, 0xFFFF, 0xE, 0, 0, 0)
    return cm.data_block(v, 0x0000)


def heartbeat_query(txn):
    # queryStatus: nibble 0x2, typeId 0xFFFF  (matches capture poll)
    return cm.data_block(cm.query_status(txn=txn, typeid=0xFFFF), 0x0000)


async def main(color, seconds):
    dev = await find_device("LA", None)
    if not dev:
        print("no bulb found"); return 1
    async with BleakClient(dev) as client:
        svc, wc, rc = pick_chars(client)
        no_resp = "write-without-response" in wc.properties
        # subscribe to notifications like the app does (CCCD enable) - the ball may
        # only hold a stable state when it sees a subscribed controller.
        nsub = 0
        for c in svc.characteristics:
            if "notify" in c.properties:
                try:
                    await client.start_notify(c, lambda _h, _d: None)
                    nsub += 1
                except Exception:  # noqa: BLE001
                    pass
        print(f"connected; subscribed {nsub} notify chars; holding color={color} {seconds}s")

        async def tx(payload):
            # write-WITH-response so both split halves are delivered and ordered
            pkt = cm.make_packet(payload, next_seq(), source=SRC)
            if len(pkt) > 20 and rc is not None:
                await client.write_gatt_char(wc, pkt[:20], response=True)
                await client.write_gatt_char(rc, pkt[20:], response=True)
            else:
                await client.write_gatt_char(wc, pkt, response=True)

        # apply steady ONCE (like the app), then continuously poll both messages
        await tx(steady(color, 1))
        await asyncio.sleep(0.3)
        print("steady applied; now streaming app-style polls (sendSelect+queryStatus)")
        txn = 2
        loops = int(seconds / 0.5)
        for _ in range(loops):
            await tx(heartbeat_select(txn))
            await tx(heartbeat_query(txn))
            txn = txn % 15 + 1
            await asyncio.sleep(0.5)
        print("done (connection closing)")
    return 0


if __name__ == "__main__":
    color = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    sys.exit(asyncio.run(main(color, secs)))
