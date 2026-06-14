# LED Ball — Raspberry Pi controller setup

Runs the BLE controller next to the ball and bridges it to Home Assistant over MQTT.
Tested logic; the Pi is the target host because macOS CoreBluetooth introduces a
random "blink off" the Pi/BlueZ stack should avoid (see SURVEY.md).

## 1. Prereqs (Raspberry Pi OS / any Linux with BlueZ)
```bash
sudo apt update
sudo apt install -y python3-venv bluez
# make sure the BLE adapter is up:
hciconfig            # or: bluetoothctl show
```

## 2. Install
```bash
git clone <this repo> ~/lightball   # or copy the folder over
cd ~/lightball
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Smoke test (no MQTT needed)
```bash
.venv/bin/python controller.py scan          # should list 'LAB....' with rssi
.venv/bin/python controller.py solid 12       # solid purple
.venv/bin/python controller.py off
.venv/bin/python controller.py hold 12 60     # hold purple 60s (watch for the blink)
```
On Linux, bleak uses the device MAC (AA:BB:CC:..). Grab it from `scan` and you can pass
`--address` to skip scanning (faster, more reliable).

`hold` is the key test: if the ball stays **rock-steady** on the Pi (unlike macOS),
we've confirmed the blink was a CoreBluetooth artifact and we're done with that issue.

## 4. Home Assistant MQTT bridge
Point these at your broker (the one HA's MQTT integration uses):
```bash
MQTT_HOST=192.168.x.x MQTT_USER=ha MQTT_PASS=secret \
  .venv/bin/python mqtt_bridge.py
```
HA will auto-discover a light named **"LED Ball"** (on/off, brightness, effect list).

## 5. Run as a service
```bash
sudo cp lightball-bridge.service /etc/systemd/system/
sudo nano /etc/systemd/system/lightball-bridge.service   # set paths/user/MQTT env
sudo systemctl daemon-reload
sudo systemctl enable --now lightball-bridge
journalctl -u lightball-bridge -f
```

## Notes / TODO
- Color & effect-mode indices are only partially mapped (purple=12, multicolor=28,
  steady=mode 2). Extend `COLORS` in `controller.py` and `EFFECTS` in `mqtt_bridge.py`
  once mapped — a quick btsnoop capture of tapping each swatch/mode gives the rest.
- If the Pi also shows the blink, we can drop BlueZ connection-interval/supervision
  hints via `bluetoothctl`/connection params; flag it and we'll tune.
