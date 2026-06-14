#!/usr/bin/env python3
"""
Home Assistant MQTT bridge for the Holiday Show Home LED Ball.

Runs on the Pi next to the ball, holds a persistent BLE connection (controller.py),
and exposes the ball to Home Assistant as an auto-discovered MQTT light:
  - on / off
  - brightness (mapped to the ball's 5 levels)
  - RGB color  (snapped to the ball's nearest palette color)
  - effect     (the animation modes + the special/holiday palette colors)

HA just needs the MQTT integration pointed at the same broker; no custom component.

Env vars (or edit DEFAULTS below):
  MQTT_HOST (192.168.168.50)  MQTT_PORT (1883)  MQTT_USER  MQTT_PASS
  BALL_ADAPTER (hci1)         BALL_ADDRESS (optional, else discover by name)
"""

import asyncio
import json
import logging
import os

import paho.mqtt.client as mqtt

import controller as ctl
from controller import LightBall

log = logging.getLogger("lightball.mqtt")

DEVICE_ID = "led_ball"
DISCO = f"homeassistant/light/{DEVICE_ID}/config"
STATE_T = f"lightball/{DEVICE_ID}/state"
CMD_T = f"lightball/{DEVICE_ID}/set"
AVAIL_T = f"lightball/{DEVICE_ID}/availability"

# Approx RGB for the ball's 16 *solid* palette colors (index 0-15), for nearest-match.
SOLID_RGB = {
    0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255), 3: (255, 140, 0), 4: (255, 105, 180),
    5: (0, 200, 200), 6: (255, 215, 0), 7: (255, 0, 200), 8: (124, 252, 0),
    9: (255, 0, 255), 10: (0, 255, 255), 11: (255, 255, 0), 12: (150, 0, 200),
    13: (255, 255, 255), 14: (210, 225, 255), 15: (240, 255, 255),
}
# Animation modes (applied to the current color).
MODE_EFFECTS = {f"Mode: {n.title()}": i for n, i in ctl.MODES.items()}
# Special/holiday palette "colors" (16-28) surfaced as effects.
SPECIAL_COLOR_EFFECTS = {
    "Spring": 16, "Summer": 17, "Autumn": 18, "Winter": 19, "Christmas": 20,
    "Valentine's": 21, "Independence": 22, "Thanksgiving": 23, "St. Patrick's": 24,
    "Halloween": 25, "Sun": 26, "Earth": 27, "MultiColor": 28,
}
EFFECT_LIST = list(MODE_EFFECTS) + list(SPECIAL_COLOR_EFFECTS)

# brightness: HA 0-255 -> ball level 0-4
def ha_to_level(v):
    return max(0, min(4, round(v / 255 * 4)))
def level_to_ha(lvl):
    return round(lvl / 4 * 255)

def nearest_solid(r, g, b):
    return min(SOLID_RGB, key=lambda i: sum((a - c) ** 2 for a, c in zip(SOLID_RGB[i], (r, g, b))))


def discovery_payload():
    return {
        "name": "LED Ball", "unique_id": DEVICE_ID, "schema": "json",
        "command_topic": CMD_T, "state_topic": STATE_T, "availability_topic": AVAIL_T,
        "brightness": True, "brightness_scale": 255,
        "supported_color_modes": ["rgb"],
        "effect": True, "effect_list": EFFECT_LIST,
        "device": {"identifiers": [DEVICE_ID], "name": "Holiday Show Home LED Ball",
                   "manufacturer": "Willis Electric / Kupoint", "model": "AL96 (CSRmesh)"},
    }


class Bridge:
    def __init__(self):
        self.ball = LightBall(address=os.environ.get("BALL_ADDRESS"),
                              adapter=os.environ.get("BALL_ADAPTER", "hci1"),
                              keepalive=True)
        self.loop = None
        # tracked state
        self.on = False
        self.color = 0          # palette index
        self.mode = ctl.MODE_STEADY
        self.level = ctl.BRIGHT_DEFAULT
        self.rgb = (255, 0, 0)
        self.effect = "Mode: Steady"
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lightball-bridge")
        u, pw = os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASS")
        if u:
            self.mqtt.username_pw_set(u, pw)
        self.mqtt.will_set(AVAIL_T, "offline", retain=True)
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_message = self._on_message

    def _publish_state(self):
        st = {"state": "ON" if self.on else "OFF", "brightness": level_to_ha(self.level),
              "color_mode": "rgb", "color": {"r": self.rgb[0], "g": self.rgb[1], "b": self.rgb[2]},
              "effect": self.effect}
        self.mqtt.publish(STATE_T, json.dumps(st), retain=True)

    def _on_connect(self, client, *_):
        log.info("MQTT connected; publishing discovery")
        client.publish(DISCO, json.dumps(discovery_payload()), retain=True)
        client.publish(AVAIL_T, "online", retain=True)
        client.subscribe(CMD_T)
        self._publish_state()

    def _on_message(self, client, userdata, msg):
        try:
            cmd = json.loads(msg.payload.decode())
        except ValueError:
            return
        log.info("cmd: %s", cmd)
        asyncio.run_coroutine_threadsafe(self._apply(cmd), self.loop)

    async def _apply(self, cmd):
        try:
            if cmd.get("state") == "OFF":
                self.on = False
                await self.ball.power(False)
                self._publish_state(); return
            # any other command implies ON
            if "brightness" in cmd:
                self.level = ha_to_level(cmd["brightness"])
            if "color" in cmd:
                c = cmd["color"]; self.rgb = (c["r"], c["g"], c["b"])
                self.color = nearest_solid(*self.rgb); self.mode = ctl.MODE_STEADY
                self.effect = "Mode: Steady"
            if "effect" in cmd:
                e = cmd["effect"]; self.effect = e
                if e in MODE_EFFECTS:
                    self.mode = MODE_EFFECTS[e]
                elif e in SPECIAL_COLOR_EFFECTS:
                    self.color = SPECIAL_COLOR_EFFECTS[e]; self.mode = ctl.MODE_STEADY
            # ensure on, then apply current mode+color+brightness
            if not self.on:
                await self.ball.power(True)
                self.on = True
                await asyncio.sleep(0.3)
            await self.ball.set_mode(self.mode, self.color, self.level)
        except Exception as e:  # noqa: BLE001
            log.error("apply failed: %s", e)
        self._publish_state()

    async def run(self):
        self.loop = asyncio.get_event_loop()
        log.info("connecting to ball...")
        await self.ball.connect()
        host = os.environ.get("MQTT_HOST", "192.168.168.50")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        log.info("connecting MQTT %s:%d", host, port)
        self.mqtt.connect_async(host, port)
        self.mqtt.loop_start()
        try:
            while True:
                await self.ball.ensure_connected()
                await asyncio.sleep(10)
        finally:
            self.mqtt.publish(AVAIL_T, "offline", retain=True)
            self.mqtt.loop_stop()
            await self.ball.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(Bridge().run())
