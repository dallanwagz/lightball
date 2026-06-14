#!/usr/bin/env python3
"""
lightball.py - scan for and control Holiday Showtime / Showhome CSRmesh bulbs over BLE.

Transport: macOS CoreBluetooth via bleak. Crypto/framing: csrmesh_crypto (ported from
the decompiled com.holidayshow v0.46 app). See SURVEY.md for the protocol details.

The bulbs are factory-provisioned to a fixed mesh (passphrase "686868") and advertise a
BLE name starting with "LA". No pairing/association is needed - power them on and send.

Usage:
    python lightball.py scan
    python lightball.py on    [--name LA] [--address UUID] [--dest 0x0000] [--source 0x8000]
    python lightball.py off
    python lightball.py level <0-255>
    python lightball.py rgb <r> <g> <b> [--level 255]
    python lightball.py raw <hex-payload>          # dest(2 LE)+model bytes, pre-framing

Tips for live debugging:
    --repeat N        send the command N times (mesh is lossy / unacknowledged)
    --random-source   use a fresh random controller id (sidesteps replay/seq history)
    --seq N           force a specific 24-bit sequence number
    --listen          subscribe to notifications and print anything the mesh sends back
"""

import argparse
import asyncio
import json
import os
import random
import sys

from bleak import BleakClient, BleakScanner

import csrmesh_crypto as cm

SERVICE = "0000fef1-0000-1000-8000-00805f9b34fb"
# control-point characteristics, in (primary, retry) preference order per ae.java
CP_PRIMARY = ["0000d011-d102-11e1-9b23-00025b00a5a5",   # newer GATT (preferred)
              "c4edc000-9daf-11e3-8004-00025b000b00"]   # older GATT fallback
CP_RETRY = ["0000d012-d102-11e1-9b23-00025b00a5a5",
            "c4edc000-9daf-11e3-8003-00025b000b00"]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".lightball_state.json")


# --- sequence number persistence (keep it monotonic across one-shot runs) ----

def next_seq() -> int:
    try:
        with open(STATE_FILE) as f:
            seq = json.load(f).get("seq", 0)
    except (OSError, ValueError):
        seq = random.randint(0x000100, 0x00FFFF)
    seq = (seq + 1) & 0xFFFFFF
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"seq": seq}, f)
    except OSError:
        pass
    return seq


# --- discovery ---------------------------------------------------------------

async def find_device(name_prefix, address, timeout=25.0):
    """Return a BLEDevice (or address str). Uses a callback scanner that returns the
    instant a matching bulb appears - the bulb advertises infrequently, so waiting a
    fixed window often misses it. If --address is given, connect directly."""
    if address:
        print(f"using address {address} directly (no scan)")
        return address

    print(f"scanning up to {timeout:.0f}s for a bulb"
          f"{f' (name {name_prefix!r} or fef1 service)' if name_prefix else ''}...")
    hit = asyncio.get_event_loop().create_future()

    def _cb(dev, adv):
        nm = adv.local_name or dev.name or ""
        svc = [u.lower() for u in (adv.service_uuids or [])]
        if (name_prefix and nm.upper().startswith(name_prefix.upper())) or SERVICE in svc:
            if not hit.done():
                print(f"  found {nm!r} addr={dev.address} rssi={adv.rssi}")
                hit.set_result(dev)

    scanner = BleakScanner(detection_callback=_cb)
    await scanner.start()
    try:
        return await asyncio.wait_for(hit, timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        await scanner.stop()


async def cmd_scan(timeout=8.0):
    print(f"scanning {timeout:.0f}s (showing all devices; *=looks like a bulb)...")
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    rows = []
    for dev, adv in found.values():
        nm = adv.local_name or dev.name or ""
        svc = [u.lower() for u in (adv.service_uuids or [])]
        bulb = (nm.upper().startswith("LA")) or (SERVICE in svc)
        rows.append((bulb, nm, dev.address, adv.rssi, SERVICE in svc))
    rows.sort(key=lambda r: (r[0], r[3] or -999), reverse=True)
    print(f"{'':2} {'name':22} {'address':40} {'rssi':>5} fef1")
    for bulb, nm, addr, rssi, hassvc in rows:
        print(f"{'*' if bulb else ' ':2} {nm[:22]:22} {addr:40} {str(rssi):>5} {hassvc}")
    print(f"\n{sum(r[0] for r in rows)} likely bulb(s), {len(rows)} device(s) total")


# --- characteristic selection ------------------------------------------------

def pick_chars(client):
    svc = None
    for s in client.services:
        if s.uuid.lower() == SERVICE:
            svc = s
            break
    if svc is None:
        raise RuntimeError(f"service {SERVICE} not found. services present: "
                           f"{[s.uuid for s in client.services]}")
    by_uuid = {c.uuid.lower(): c for c in svc.characteristics}
    write_char = next((by_uuid[u] for u in CP_PRIMARY if u in by_uuid), None)
    retry_char = next((by_uuid[u] for u in CP_RETRY if u in by_uuid), None)
    if write_char is None:
        raise RuntimeError("no known control-point characteristic found. present: "
                           f"{list(by_uuid)}")
    return svc, write_char, retry_char


# --- send --------------------------------------------------------------------

async def send(args, make_payload):
    dev = await find_device(args.name, args.address)
    if dev is None:
        print("no bulb found. Try `scan`, move closer, or pass --address.", file=sys.stderr)
        return 1
    print(f"connecting to {dev.name or '?'} [{dev.address}] ...")
    async with BleakClient(dev) as client:
        svc, write_char, retry_char = pick_chars(client)
        props = ",".join(write_char.properties)
        print(f"service {svc.uuid}\n write -> {write_char.uuid} ({props})"
              f"{'  retry -> ' + retry_char.uuid if retry_char else ''}")

        if args.listen and "notify" in write_char.properties:
            def _on_notify(_, data):
                print("  notify:", data.hex())
            try:
                await client.start_notify(write_char, _on_notify)
                print(" notifications enabled")
            except Exception as e:  # noqa: BLE001
                print(" notify failed:", e)

        source = random.randint(0x8001, 0xBFFF) if args.random_source else args.source
        no_resp = "write-without-response" in write_char.properties
        for n in range(args.repeat):
            seq = args.seq if args.seq is not None else next_seq()
            payload = make_payload(n) if callable(make_payload) else make_payload
            pkt = cm.make_packet(payload, seq, source=source)
            # The app splits packets >20 bytes across the two control points
            # (first 20 bytes to one, remainder to the other). Single writes of
            # long packets are silently dropped by the ball.
            if len(pkt) > 20 and retry_char is not None:
                await client.write_gatt_char(write_char, pkt[:20], response=not no_resp)
                await client.write_gatt_char(retry_char, pkt[20:], response=not no_resp)
            else:
                await client.write_gatt_char(write_char, pkt, response=not no_resp)
            print(f"  sent #{n+1} seq=0x{seq:06x} src=0x{source:04x} "
                  f"({'no-resp' if no_resp else 'resp'}): {pkt.hex()}")
            if args.repeat > 1:
                await asyncio.sleep(0.15)
        if args.listen:
            await asyncio.sleep(1.5)
    return 0


# --- arg parsing -------------------------------------------------------------

def auto_int(x):
    return int(x, 0)


def build_parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--name", default="LA", help="advertised-name prefix (default LA)")
        sp.add_argument("--address", help="connect to this BLE address/UUID directly")
        sp.add_argument("--dest", type=auto_int, default=cm.BROADCAST,
                        help="mesh device id (default 0x0000 = broadcast/all)")
        sp.add_argument("--source", type=auto_int, default=cm.DEFAULT_SOURCE,
                        help="controller source id (default 0x8000)")
        sp.add_argument("--random-source", action="store_true",
                        help="use a fresh random source (sidesteps seq/replay history)")
        sp.add_argument("--seq", type=auto_int, default=None,
                        help="force a 24-bit sequence number")
        sp.add_argument("--repeat", type=int, default=3, help="send N times (default 3)")
        sp.add_argument("--listen", action="store_true",
                        help="subscribe to notifications and print responses")

    sp = sub.add_parser("scan", help="list nearby BLE devices")
    sp.add_argument("--timeout", type=float, default=8.0)

    for name in ("on", "off"):
        add_common(sub.add_parser(name, help=f"power {name}"))

    sp = sub.add_parser("level", help="set brightness 0-255")
    sp.add_argument("value", type=auto_int)
    add_common(sp)

    sp = sub.add_parser("rgb", help="set color (24-byte packet; may need MTU split)")
    for c in ("r", "g", "b"):
        sp.add_argument(c, type=auto_int)
    sp.add_argument("--level", type=auto_int, default=0xFF)
    add_common(sp)

    sp = sub.add_parser("raw", help="send a raw payload: dest(2 LE)+model bytes, hex")
    sp.add_argument("hexpayload")
    add_common(sp)

    # vendor DataModel effect-engine commands
    sp = sub.add_parser("solid", help="set Steady/solid mode (vendor commondMode mode 0)")
    sp.add_argument("--color", type=auto_int, default=1, help="palette color index (default 1)")
    sp.add_argument("--typeid", type=auto_int, default=cm.TYPE_ALL)
    add_common(sp)

    sp = sub.add_parser("mode", help="set vendor effect mode by index (commondMode)")
    sp.add_argument("index", type=auto_int)
    sp.add_argument("--color", type=auto_int, default=1)
    sp.add_argument("--speed", type=auto_int, default=0)
    sp.add_argument("--typeid", type=auto_int, default=cm.TYPE_ALL)
    add_common(sp)

    sp = sub.add_parser("show", help="select a 'show' display mode (showView)")
    sp.add_argument("index", type=auto_int)
    sp.add_argument("--color", type=auto_int, default=0)
    sp.add_argument("--typeid", type=auto_int, default=cm.TYPE_SHOW)
    add_common(sp)

    sp = sub.add_parser("vendor", help="send a raw 10-byte vendor payload (hex) via DataModel")
    sp.add_argument("hexvendor")
    add_common(sp)

    return p


def main():
    args = build_parser().parse_args()
    if args.cmd == "scan":
        return asyncio.run(cmd_scan(args.timeout))

    def roll_txn(n):
        return (n % 15) + 1   # rolling 1..15 transaction nibble, like the app

    if args.cmd == "on":
        payload = cm.power(cm.POWER_ON, args.dest)
    elif args.cmd == "off":
        payload = cm.power(cm.POWER_OFF, args.dest)
    elif args.cmd == "level":
        payload = cm.set_level(args.value, args.dest)
    elif args.cmd == "rgb":
        payload = cm.set_rgb(args.r, args.g, args.b, args.level, dest=args.dest)
    elif args.cmd == "raw":
        payload = bytes.fromhex(args.hexpayload)
    elif args.cmd == "solid":
        payload = lambda n: cm.data_block(
            cm.commond_mode(0, args.color, 0, txn=roll_txn(n), typeid=args.typeid), args.dest)
    elif args.cmd == "mode":
        payload = lambda n: cm.data_block(
            cm.commond_mode(args.index, args.color, args.speed, txn=roll_txn(n),
                            typeid=args.typeid), args.dest)
    elif args.cmd == "show":
        payload = lambda n: cm.data_block(
            cm.show_view(args.index, args.color, txn=roll_txn(n), typeid=args.typeid), args.dest)
    elif args.cmd == "vendor":
        payload = cm.data_block(bytes.fromhex(args.hexvendor), args.dest)
    else:
        return 2
    return asyncio.run(send(args, payload))


if __name__ == "__main__":
    sys.exit(main())
