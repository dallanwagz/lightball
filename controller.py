#!/usr/bin/env python3
"""
LightBall controller - a reusable async controller for Holiday Showtime CSRmesh
"LED Ball" devices, designed to run as a long-lived service on a Linux/BlueZ host
(Raspberry Pi) and back a Home Assistant integration.

Portable across BlueZ (Pi) and CoreBluetooth (macOS) via bleak. Wraps everything we
reverse-engineered: the 686868 network key, the DataModel vendor commands, the
two-control-point packet split, and connection management for an intermittently
advertising, flaky-to-connect device.

See SURVEY.md for the protocol details and how this was derived.
"""

import asyncio
import logging
import random

from bleak import BleakClient, BleakScanner

import csrmesh_crypto as cm

log = logging.getLogger("lightball")

SERVICE = "0000fef1-0000-1000-8000-00805f9b34fb"
# control-point characteristics in (primary, secondary) order. A packet >20 bytes is
# split: first 20 bytes -> primary, remainder -> secondary (matches the app).
CP_PRIMARY = ["0000d011-d102-11e1-9b23-00025b00a5a5",   # newer GATT generation
              "c4edc000-9daf-11e3-8004-00025b000b00"]   # older generation (our ball)
CP_SECONDARY = ["0000d012-d102-11e1-9b23-00025b00a5a5",
                "c4edc000-9daf-11e3-8003-00025b000b00"]

# --- product specifics for the LED Ball (typeId 0xfc7b in the shipping app) ---
LED_BALL_TYPEID = 0xFC7B
MODE_STEADY = 2          # commondMode mode index that yields a solid (non-animated) color

# Known palette indices (b6). Partial - extend as we map them.
COLORS = {
    "purple": 12,
    "multicolor": 28,    # animated rainbow
}
# Effect/mode names are still being mapped; expose raw indices meanwhile.


class LightBall:
    """Async controller for one LED Ball. Maintains a persistent connection and
    auto-reconnects (the device advertises intermittently and drops easily)."""

    def __init__(self, address=None, name_prefix="LAB", typeid=LED_BALL_TYPEID,
                 source=None, keepalive=True, adapter=None):
        self.address = address
        self.name_prefix = name_prefix
        self.typeid = typeid
        # Use a fresh random controller source (NOT 0x8000) so the ball has no
        # sequence-number history for it and accepts every packet. Reusing the
        # phone's 0x8000 with a lower seq triggers replay rejection (commands
        # silently ignored). 0x8000-0xBFFF is the controller address range.
        self.source = source if source is not None else random.randint(0x8001, 0xBFFE)
        self.keepalive = keepalive
        self.adapter = adapter          # e.g. "hci1" on Linux/BlueZ; None = default
        self.key = cm.DEFAULT_KEY
        self._client = None
        self._write = None
        self._secondary = None
        self._seq = random.randint(0x010000, 0xF00000)   # high start avoids replay window
        self._txn = 0
        self._lock = asyncio.Lock()
        self._ka_task = None

    # --- connection -------------------------------------------------------

    async def _find(self, timeout=25.0):
        # Always scan to get a live device handle - on BlueZ, connecting by raw
        # address fails unless the device was very recently advertised/cached.
        fut = asyncio.get_event_loop().create_future()

        def cb(dev, adv):
            nm = adv.local_name or dev.name or ""
            svc = [u.lower() for u in (adv.service_uuids or [])]
            if self.address:
                match = dev.address.upper() == self.address.upper()
            else:
                match = nm.upper().startswith(self.name_prefix.upper()) or SERVICE in svc
            if match and not fut.done():
                fut.set_result(dev)

        kw = {"adapter": self.adapter} if self.adapter else {}
        scanner = BleakScanner(detection_callback=cb, **kw)
        await scanner.start()
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            await scanner.stop()

    def _pick_chars(self):
        svc = next((s for s in self._client.services if s.uuid.lower() == SERVICE), None)
        if svc is None:
            raise RuntimeError(f"service {SERVICE} not found")
        by = {c.uuid.lower(): c for c in svc.characteristics}
        self._write = next((by[u] for u in CP_PRIMARY if u in by), None)
        self._secondary = next((by[u] for u in CP_SECONDARY if u in by), None)
        if self._write is None:
            raise RuntimeError(f"no control-point characteristic; have {list(by)}")
        # subscribe to notifications like the app does
        for c in svc.characteristics:
            if "notify" in c.properties:
                try:
                    asyncio.create_task(self._client.start_notify(c, lambda *_: None))
                except Exception:  # noqa: BLE001
                    pass

    async def connect(self, attempts=10):
        for i in range(attempts):
            client = None
            try:
                dev = await self._find()
                if dev is None:
                    log.warning("ball not found (scan %d/%d)", i + 1, attempts)
                    continue
                log.info("connecting to %s", getattr(dev, "address", dev))
                kw = {"adapter": self.adapter} if self.adapter else {}
                client = BleakClient(dev, disconnected_callback=self._on_disconnect, **kw)
                await client.connect()
                self._client = client
                self._pick_chars()
                log.info("connected; write=%s", self._write.uuid)
                if self.keepalive and not self._ka_task:
                    self._ka_task = asyncio.create_task(self._keepalive_loop())
                return True
            except Exception as e:  # noqa: BLE001
                log.warning("connect attempt %d failed: %s", i + 1, e)
                self._client = None
                if client is not None:
                    try:
                        await client.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                await asyncio.sleep(2.5)   # let BlueZ settle before retrying
        return False

    def _on_disconnect(self, _client):
        log.warning("disconnected")
        self._client = None

    async def disconnect(self):
        if self._ka_task:
            self._ka_task.cancel()
            self._ka_task = None
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def ensure_connected(self):
        if self._client is None or not self._client.is_connected:
            await self.connect()

    # --- low-level send ---------------------------------------------------

    def _next_seq(self):
        self._seq = (self._seq + 1) & 0xFFFFFF
        return self._seq

    def _next_txn(self):
        self._txn = self._txn % 15 + 1
        return self._txn

    async def _send_packet(self, payload, response=False):
        """make_packet + two-control-point split write."""
        await self.ensure_connected()
        pkt = cm.make_packet(payload, self._next_seq(), source=self.source)
        async with self._lock:
            if len(pkt) > 20 and self._secondary is not None:
                await self._client.write_gatt_char(self._write, pkt[:20], response=response)
                await self._client.write_gatt_char(self._secondary, pkt[20:], response=response)
            else:
                await self._client.write_gatt_char(self._write, pkt, response=response)

    async def _send_vendor(self, vendor, dest=cm.BROADCAST, times=2):
        for _ in range(times):
            await self._send_packet(cm.data_block(vendor, dest))
            await asyncio.sleep(0.12)

    async def _keepalive_loop(self):
        """Light poll to keep the controller "present" (mirrors the app's heartbeat)."""
        try:
            while True:
                await asyncio.sleep(2.0)
                if self._client and self._client.is_connected:
                    try:
                        v = cm._vendor(self._next_txn(), 0, 0xFFFF, 0xE, 0, 0, 0)
                        await self._send_packet(cm.data_block(v, cm.BROADCAST))
                    except Exception:  # noqa: BLE001
                        pass
        except asyncio.CancelledError:
            pass

    # --- high-level API ---------------------------------------------------

    async def solid(self, color, dest=cm.BROADCAST):
        """Set a steady (non-animated) solid color by palette index."""
        v = cm.commond_mode(MODE_STEADY, color, 2, txn=self._next_txn(), typeid=self.typeid)
        await self._send_vendor(v, dest, times=3)

    async def set_mode(self, mode, color, speed=0, dest=cm.BROADCAST):
        """Set a commondMode effect: mode index, palette color, speed."""
        v = cm.commond_mode(mode, color, speed, txn=self._next_txn(), typeid=self.typeid)
        await self._send_vendor(v, dest, times=3)

    async def set_show(self, mode, color, dest=cm.BROADCAST):
        """Set a showView display mode (mode 0-2 family)."""
        v = cm.show_view(mode, color, txn=self._next_txn(), typeid=self.typeid)
        await self._send_vendor(v, dest, times=3)

    async def power(self, on, dest=cm.BROADCAST):
        """Standard CSRmesh Power model on/off (works without the vendor path)."""
        msg = cm.power(cm.POWER_ON if on else cm.POWER_OFF, dest)
        await self._send_packet(msg)
        await self._send_packet(msg)

    async def brightness(self, level, dest=cm.BROADCAST):
        """Standard CSRmesh Light model brightness 0-255."""
        await self._send_packet(cm.set_level(level, dest))
        await self._send_packet(cm.set_level(level, dest))


# --- CLI --------------------------------------------------------------------

async def _cli():
    import argparse
    p = argparse.ArgumentParser(description="LED Ball controller (Pi-ready)")
    p.add_argument("--address", help="BLE address/MAC (skip scan)")
    p.add_argument("--adapter", help="BlueZ adapter, e.g. hci1 (Linux)")
    p.add_argument("--source", type=lambda x: int(x, 0), default=None,
                   help="controller source id; default = fresh random (avoids replay)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    s = sub.add_parser("solid"); s.add_argument("color", type=lambda x: int(x, 0))
    s = sub.add_parser("mode"); s.add_argument("mode", type=int); s.add_argument("color", type=int); s.add_argument("--speed", type=int, default=0)
    s = sub.add_parser("show"); s.add_argument("mode", type=int); s.add_argument("color", type=int)
    s = sub.add_parser("brightness"); s.add_argument("level", type=lambda x: int(x, 0))
    for n in ("on", "off"):
        sub.add_parser(n)
    s = sub.add_parser("hold"); s.add_argument("color", type=lambda x: int(x, 0)); s.add_argument("seconds", type=float, nargs="?", default=30.0)
    args = p.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "scan":
        found = await BleakScanner.discover(timeout=10.0, return_adv=True)
        for dev, adv in found.values():
            nm = adv.local_name or dev.name or ""
            if nm.upper().startswith("LA") or SERVICE in [u.lower() for u in (adv.service_uuids or [])]:
                print(f"* {nm:18} {dev.address}  rssi={adv.rssi}")
        return

    ball = LightBall(address=args.address, source=args.source,
                     adapter=args.adapter, keepalive=(args.cmd == "hold"))
    if not await ball.connect():
        print("could not connect to the ball"); return
    try:
        if args.cmd == "solid":
            await ball.solid(args.color)
        elif args.cmd == "mode":
            await ball.set_mode(args.mode, args.color, args.speed)
        elif args.cmd == "show":
            await ball.set_show(args.mode, args.color)
        elif args.cmd == "brightness":
            await ball.brightness(args.level)
        elif args.cmd == "on":
            await ball.power(True)
        elif args.cmd == "off":
            await ball.power(False)
        elif args.cmd == "hold":
            await ball.solid(args.color)
            print(f"holding color {args.color} for {args.seconds}s")
            await asyncio.sleep(args.seconds)
        await asyncio.sleep(0.5)
    finally:
        await ball.disconnect()


if __name__ == "__main__":
    asyncio.run(_cli())
