# Cracking a $20 Light Ball: From APK to Home Assistant

A $20 holiday light orb from Home Depot ships with AES-128 encryption, an authenticated message integrity check, and a network key that is identical on every unit in the product line. Here is how I reverse-engineered it into a first-class Home Assistant device, with no app, no cloud, and no dedicated Bluetooth hardware of my own.

Out of the box, the only way to control it is a phone app called "Show APP." There's no web API, no Home Assistant integration, and nothing on GitHub. Just the app and a glowing sphere. I wanted it on my dashboard next to everything else, so I took the long way around.

What follows is the speed-run: the milestones that mattered, not the dead ends.

## Getting the app, and what it was hiding

You can't reverse engineer what you can't read. The app isn't on any APK mirror, so I pulled it straight off my Android phone over ADB and ran it through [jadx](https://github.com/skylot/jadx) to turn the Dalvik bytecode back into readable Java:

```bash
adb shell pm path com.tcdtech.ishowlight
adb pull /data/app/.../base.apk show-app.apk
```

The imports gave the game away immediately: `com.csr.csrmesh2`. This is CSRmesh, Qualcomm/CSR's old Bluetooth mesh protocol. That single clue shaped the whole project, because it meant I wasn't staring at a homebrew byte format. It was a documented (if obscure) mesh stack with actual crypto underneath.

At the GATT layer the ball exposes service `0xFEF1` with two "control point" characteristics: one ending in `8003` for the first chunk of a packet, and one ending in `8004` for the remainder. Keep that two-characteristic split in mind, because it's where things went wrong later.

## Recovering the crypto

CSRmesh doesn't send anything in the clear. Every packet is encrypted and authenticated with a key derived from the network passphrase. Tracing the derivation code, the recipe is: SHA-256 the passphrase plus a `\x00MCP` salt, reverse all 32 bytes of the digest, and keep the first 16.

```python
network_key = bytes(reversed(sha256(passphrase + b"\x00MCP").digest()))[:16]
```

The passphrase baked into this product line is `686868`. It derives to `6750aae5bf990f0c660e5ed351a8cd26`. That is the security headline hiding in a toy: the key is hardcoded and shared, so every one of these orbs on Earth speaks with the same network credentials.

Each message is then AES-128 in counter mode over the payload, followed by an 8-byte MIC for authentication. The interesting wrinkle is the MIC. It isn't the AES-CCM tag the CSRmesh spec calls for (the stock library's `EncryptionUtils` wraps an `AESEngine` in a `CCMBlockCipher` for exactly that). This build computes the packet MIC with `HmacSHA256` instead, then byte-reverses and truncates it to 8 bytes. Off-spec, but consistent, and once I matched it my forged packets authenticated cleanly. A trailing `0xFF` byte marks the end of the frame.

## Decoding the commands

The app's `Commands` class speaks a vendor "DataModel" message, opcode `0x73`. The workhorse is `commonMode(mode, color, brightness)`:

| field | meaning |
|------|---------|
| `mode` | 0 = off, 1 = steady, 2 = blink, 3 = sparkle, 5 = fade, 7 = waves |
| `color` | palette index: 0 = red, 1 = green, 2 = blue, up to 28 = MultiColor |
| `brightness` | level 0 to 4, sent on the wire as `4 - level`, which cost me an hour |

There's also a `sendSelect` handshake the app fires before commands, and a separate `showView` message for the canned holiday animations. So now I had a theory of the whole protocol, but nothing I'd written had lit up an actual ball yet.

## Letting the real app show me the answer

Instead of guessing, I made the official app generate ground-truth traffic and recorded it. I turned on Android's Bluetooth HCI snoop log, then drove the app hands-free through ADB's accessibility tooling (tapping on, picking colors, starting shows) while it logged every byte going to the ball. Then I parsed `btsnoop_hci.log` and lined the captured packets up against the ones my Python was generating.

That capture was the turning point, and it told me two things. First, my crypto was correct: captured packets decrypted cleanly with my derived key. Second, and this is the one that had been killing me, packets longer than 20 bytes are split across both control-point characteristics, and the order is the reverse of what I'd assumed. The first 20 bytes go to `8003`, the remainder to `8004`. I'd had it backwards, so the ball was getting half a packet and silently dropping it.

## First light

With the split-write fixed, I scripted a [bleak](https://github.com/hbldh/bleak) scan-and-send, and a few more gremlins surfaced. The ball randomizes its MAC, so pinning an address is useless; it does keep a stable advertised name (`LAB00001CEB11`), so I discover it by name every time. Reusing a low sequence counter got commands ignored by replay protection, which a fresh random source per session fixed. And "steady" turned out to be mode 1, not 2. Mode 2 is blink.

Then it worked. I sent a packet and the ball went solid red and held steady, then cycled to green on command. After weeks of reading decompiled Java, watching a physical object obey a script I wrote was a genuinely good feeling.

## Making it a real Home Assistant integration

A one-off script is fun, but I wanted this living in Home Assistant like any other light, and working even though my HA server has no Bluetooth radio anywhere near the ball.

That last constraint is where ESPHome Bluetooth proxies earn their keep. An ESP32 flashed as a proxy relays BLE for Home Assistant, so any HA-managed Bluetooth connection routes through it transparently. The trick is to build on Home Assistant's own Bluetooth stack instead of raw bleak, because then proxy support comes for free.

So I wrote a proper custom component. It discovers the ball by its stable local name (matching `LAB*` and service `0xFEF1`) with a config-flow confirm step, so there's no manual MAC entry. It connects through `bleak-retry-connector` and HA's Bluetooth APIs, which means every connection rides the ESP32 proxy automatically. And it exposes a `light` entity with on/off, RGB snapped to the nearest palette color, brightness, and the full effect list. I packaged it for HACS, installed it on my live instance, and turned the ball on from a dashboard card. The command left HA, hopped through an ESP32 across the house, and landed on the orb.

One bug held out. MultiColor and the holiday presets came up as flat solid red instead of cycling. The decompiled `ColorData` had the answer, and it was a category error in my own code: the app keeps two separate lists. There's a color palette applied with `commonMode`, and a list of animated *shows* (Christmas, Halloween, MultiColor) applied with the entirely separate `showView` message. I'd been sending the shows as if they were palette colors, so the firmware just grabbed the lead color and sat there. Routing them through `showView` made MultiColor cycle and the Christmas show do its red/green/white chase.

## Where it landed

The full arc, end to end:

> **APK → jadx → CSRmesh → key & packet crypto → HCI snoop capture → split-write fix → bleak first light → HA custom component → ESPHome BT proxy → HACS.**

A $20 light ball with a closed phone app is now discovered automatically by Home Assistant and controlled through a Bluetooth proxy with no extra hardware, exposing every color, brightness level, animation mode, and holiday show the original app could.

The lesson I keep relearning: when you're stuck guessing at a protocol, stop guessing and make the legitimate client show you the answer. One afternoon of packet captures beat a week of reading decompiled code.

What's your go-to when a closed protocol won't cooperate: decompile first, or capture first?
