# Home Assistant integration (native, via Bluetooth proxy)

A custom HA integration that controls the LED Ball over Bluetooth using Home
Assistant's own Bluetooth stack — so it works through an **ESPHome Bluetooth Proxy**
placed near the ball. No Pi, no MQTT, no dongle: a native light entity.

## 1. Put a Bluetooth proxy near the ball

The ball's transmit power is very low (~0.8 mW), so the proxy must be close (same
room, ideally a few meters, line-of-sight). Flash any ESP32 with the ESPHome
**Bluetooth Proxy** (https://esphome.io/projects/?type=bluetooth) — the ready-made
"Bluetooth Proxy" project works — and adopt it into Home Assistant. Confirm it shows
up under Settings → Devices & Services → ESPHome with active connections enabled.

(HA's own built-in/USB Bluetooth adapter also works if it's in range of the ball.)

## 2. Install the integration

Copy the component into your HA config and restart:

```
config/custom_components/lightball/        <-- copy this whole folder here
```
e.g. `scp -r custom_components/lightball  <ha>:/config/custom_components/` (HA OS:
use the Samba/SSH add-on). Then restart Home Assistant.

`bleak-retry-connector` is pulled in automatically (it's in `manifest.json`).

## 3. Add the device

- Power the ball on (Function button) within range of the proxy.
- HA should **auto-discover** it: Settings → Devices & Services → a "Holiday Show
  Home LED Ball" discovery → **Configure**.
- If it doesn't auto-discover, Add Integration → "Holiday Show Home LED Ball" → pick
  the `LAB…` device from the list.

It's identified by its **stable name** (`LAB00001CEB11`) because the BLE MAC rotates;
the integration resolves the current address each time via HA Bluetooth.

## 4. Use it

A normal HA **light** entity:
- **On / off**
- **Brightness** (mapped to the ball's 5 levels)
- **Color** — HA's color wheel snaps to the nearest of the ball's 16 solid colors
- **Effects** — the animation modes (Steady, Blink, Sparkle, Instead, Fade, Rolling,
  Waves, Fireworks, Polar, Color Band) plus the special palette colors (MultiColor,
  Christmas, Halloween, Spring, …)

## Notes / limitations

- State is **optimistic** (the ball doesn't reliably report back), so HA shows the
  last commanded state.
- Each command opens a short BLE connection through the proxy (a second or two of
  latency); `bleak-retry-connector` handles retries for the flaky, weak-signal radio.
- Protocol details and how this was reverse-engineered: `SURVEY.md`. The standalone
  Pi + MQTT bridge (`mqtt_bridge.py`) remains as an alternative deployment.
