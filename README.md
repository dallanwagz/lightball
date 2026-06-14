# Holiday Show Home — LED Ball (CSRmesh) reverse engineering + controller

Reverse-engineering the **Holiday Show Home "App Light Ball"** (BT model **AL96**, FCC ID
**OXGAL96**, Willis Electric / Kupoint, 2018) so it can be controlled without the vendor
app — and driven from **Home Assistant** via a small Raspberry Pi BLE bridge.

The ball is a battery-powered RGB orb that speaks **CSRmesh** (Qualcomm/CSR) over BLE. The
official `com.holidayshow` / `com.tcdtech.ishowlight` apps were decompiled to derive the
protocol; this repo contains the resulting protocol implementation, analysis tooling, and a
deployable controller. (The decompiled APK sources and packet-capture bug-reports are **not**
committed — they're third-party/copyrighted and contain personal device data.)

## What was figured out (see `SURVEY.md` for the full write-up)

- **Network key (no secret to steal):** the app hardcodes passphrase `686868`; the CSRmesh
  network key = `reverse(SHA-256(b"686868\x00MCP"))[:16]` = `6750aae5bf990f0c660e5ed351a8cd26`.
  Verified byte-exact against the app's traffic (including the HMAC MIC).
- **Transport:** CSRmesh GATT bridge, service `0000FEF1`, control-point characteristics
  `C4EDC000-…-8004` / `-8003`. Commands are encrypted MTL packets.
- **The key gotcha:** packets >20 bytes are **split across the two control-point
  characteristics** (first 20 bytes → one, remainder → the other). Single writes are silently
  dropped — this is why color/mode commands (and `setRgb`) failed until discovered via packet
  capture.
- **Control:** vendor DataModel (`0x73`) commands, typeId `0xfc7b` for the LED Ball; payload
  `[txn|3, 00, fc, 7b, txn|3, MODE, COLOR, 02, 00, 00]`. **Mode 2 = Steady (solid)**;
  **color 12 = purple**, **28 = MultiColor**. Power/brightness use the standard CSRmesh
  Power/Light models.
- **Confirmed bidirectional** — the ball decrypts our packets and replies (we decrypt those).

## Repo layout

| File | Purpose |
|---|---|
| `csrmesh_crypto.py` | CSRmesh key derivation, packet encrypt/decrypt, command builders |
| `controller.py` | **`LightBall` async controller** (connect/retry, split-write, API) + CLI — the deployable piece |
| `mqtt_bridge.py` | Home Assistant MQTT-discovery light bridge (runs on the Pi) |
| `lightball.py` | Earlier all-in-one CLI (scan/on/off/rgb/mode/show/vendor/raw) |
| `parse_btsnoop.py` | Decode an Android `btsnoop_hci.log` and decrypt the app's CSRmesh traffic |
| `probe.py`, `readback.py` | Comms probes (read the ball's state back over the reply channel) |
| `paint.py`, `solidcolor.py`, `hold.py`, `vendortest.py` | Experiment scripts used during RE |
| `SURVEY.md` | Full protocol reverse-engineering write-up |
| `HARDWARE.md` | Device label + FCC catalog |
| `PI_SETUP.md` | Raspberry Pi (BlueZ) deployment guide |
| `lightball-bridge.service` | systemd unit for the MQTT bridge |

## Quick start (Raspberry Pi + USB BLE dongle)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python controller.py --adapter hci1 scan        # find the ball (name LAB…)
.venv/bin/python controller.py --adapter hci1 solid 12     # solid purple
.venv/bin/python controller.py --adapter hci1 hold 12 60   # hold 60s
```
See `PI_SETUP.md` for full setup and the Home Assistant MQTT bridge.

## Status

Working: protocol fully reversed and verified; Pi controller connects and drives the ball
(power, brightness, solid color, modes). Open items:

- **Random "blink off"** while holding a solid color. Leading suspect: the **aged 2018 18650
  battery browning out under LED load** (test on the charger) rather than anything in the
  protocol — packets are byte-identical to the app's.
- **Color palette mapping** is partial (purple=12, multicolor=28 known); needs a short capture
  of each swatch to finish.
- BLE link is finicky — the ball advertises intermittently with a **rotating private address**
  (always discover by name `LAB…`, never a fixed MAC) and **very low TX power (~0.8 mW)**, so a
  close, dedicated BLE host is recommended.

## Notes / legal

Personal project for interoperability with hardware I own. Decompiled vendor app sources and
captured traffic are not redistributed here.
