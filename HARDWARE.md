# LED Ball — hardware catalog

From the label on the base of the unit (photo, 2026-06-13):

| Field | Value |
|---|---|
| Product name | Show Home App Light Ball |
| Brand | Holiday Show Home™ (APP-controlled) |
| Bluetooth model no. | **AL96** |
| FCC ID | **OXGAL96** (grantee code OXG = Kupoint) |
| Manufacturer | Kupoint (Dongguan) Electric Co., Ltd |
| Origin / date | Made in China, date code **0618** (June 2018) |
| Power input | UL Adapter Class II, 5V / 1A |
| Battery | **18650 Lithium, 3600 mAh** (internal, rechargeable) |
| Radio | Bluetooth "Mesh" branded — actually **CSRmesh** (per decompiled app) |
| Controls | Physical **"Function"** button on the base; USB charge lead |

## Why this matters for our work

1. **It is BATTERY-POWERED (18650, and the cell is from ~2018, likely aged).**
   This is a strong new candidate for the "random blink off": under full-LED load, a
   tired 18650 can brown-out briefly = the LEDs blink off, independent of BLE. Worth
   testing on the charger / with a known-good cell, and checking whether the blink
   correlates with brightness/load rather than our packets. (The phone app appearing
   "rock steady" may just have been at a different battery/charge state.)

2. **There is a physical "Function" button.** Likely cycles modes / power and may
   factory-reset or re-enter pairing on long-press. Use it to recover a stuck state
   instead of unplugging, and to probe default behavior. (TODO: characterize short vs
   long press.)

3. **Model AL96 / FCC ID OXGAL96.** FCC filing (applied 2018-04-24):
   - **Real grantee: Willis Electric Co., Ltd.** (OXG) — major Christmas-lights OEM
     (Home Depot brands). Kupoint = factory; Willis/Holiday Show Home = brand owner.
   - BLE 2402–2480 MHz, Part 15C. **Max conducted TX power ≈ 0.83 mW (~−0.8 dBm)** —
     very low; explains weak RSSI (~−60 up close), flaky connects, and dropped writes.
     A close, dedicated BLE host (our Pi+dongle) is the right call; keep antenna near.
   - Chip/SoC not stated in text exhibits; would be in Internal Photos / Schematic /
     Block Diagram images at fccid.io/OXGAL96 if we want to confirm the CSR part.
   - Exhibits available: Users Manual, Internal/External Photos, RF Test Report,
     RF Exposure, Setup Photos, Label/Location.

4. Confirms the product line: this is the "Show Home" / "Holiday Show Home" ecosystem,
   matching the decompiled `com.holidayshow` app and the `com.tcdtech.ishowlight`
   "Show Home App" — same CSRmesh stack, network key, and command format we reversed.
