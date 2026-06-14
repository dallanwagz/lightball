#!/usr/bin/env python3
"""
Home Assistant MQTT bridge for the LED Ball.

Runs on the Pi next to the ball, holds a persistent BLE connection via controller.py,
and exposes the ball to Home Assistant as an auto-discovered MQTT light (on/off,
brightness, and an effect list of modes + solid colors). HA needs the MQTT integration
pointed at the same broker; no custom component required.

Env vars (or edit DEFAULTS):
  MQTT_HOST (default 127.0.0.1)  MQTT_PORT (1883)  MQTT_USER  MQTT_PASS
  BALL_ADDRESS (optional, skip scan)  BALL_SOURCE (default 0x8000)

The ball is palette-based (no RGB), so "color" and "effect" are surfaced together as
HA effects. Extend EFFECTS as we finish mapping color/mode indices (see SURVEY.md).
"""

import asyncio
import json
import logging
import os

import paho.mqtt.client as mqtt

from controller import LightBall, COLORS, MODE_STEADY

log = logging.getLogger("lightball.mqtt")

DEVICE_ID = "led_ball"
DISCO = f"homeassistant/light/{DEVICE_ID}/config"
STATE_T = f"lightball/{DEVICE_ID}/state"
CMD_T = f"lightball/{DEVICE_ID}/set"
AVAIL_T = f"lightball/{DEVICE_ID}/availability"

# effect name -> async controller action. Solid colors + animation modes.
# NOTE: color/mode indices beyond these are still being mapped (SURVEY.md).
EFFECTS = {
    "Solid Purple":     lambda b: b.solid(COLORS["purple"]),
    "Solid (MultiColor)": lambda b: b.set_mode(MODE_STEADY, COLORS["multicolor"]),
    # animation modes captured (commondMode mode index, color index): names TBD
    "Mode 1":  lambda b: b.set_mode(1, COLORS["purple"]),
    "Mode 3":  lambda b: b.set_mode(3, COLORS["purple"]),
    "Mode 4 (Waves)": lambda b: b.set_mode(4, COLORS["purple"]),
    "Rainbow": lambda b: b.set_mode(4, COLORS["multicolor"]),
}
EFFECT_LIST = list(EFFECTS.keys())


def discovery_payload():
    return {
        "name": "LED Ball",
        "unique_id": DEVICE_ID,
        "schema": "json",
        "command_topic": CMD_T,
        "state_topic": STATE_T,
        "availability_topic": AVAIL_T,
        "brightness": True,
        "brightness_scale": 255,
        "effect": True,
        "effect_list": EFFECT_LIST,
        "device": {"identifiers": [DEVICE_ID], "name": "Holiday Showtime LED Ball",
                   "manufacturer": "TCD Tech", "model": "LED Ball (CSRmesh)"},
    }


class Bridge:
    def __init__(self):
        self.ball = LightBall(address=os.environ.get("BALL_ADDRESS"),
                              source=int(os.environ.get("BALL_SOURCE", "0x8000"), 0),
                              keepalive=True)
        self.loop = None
        self.state = {"state": "OFF", "brightness": 255, "effect": EFFECT_LIST[0]}
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="lightball-bridge")
        u, pw = os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASS")
        if u:
            self.mqtt.username_pw_set(u, pw)
        self.mqtt.will_set(AVAIL_T, "offline", retain=True)
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_message = self._on_message

    def _on_connect(self, client, *_):
        log.info("MQTT connected; publishing discovery")
        client.publish(DISCO, json.dumps(discovery_payload()), retain=True)
        client.publish(AVAIL_T, "online", retain=True)
        client.subscribe(CMD_T)
        client.publish(STATE_T, json.dumps(self.state), retain=True)

    def _on_message(self, client, userdata, msg):
        try:
            cmd = json.loads(msg.payload.decode())
        except ValueError:
            return
        log.info("cmd: %s", cmd)
        # schedule the async handler on the asyncio loop
        asyncio.run_coroutine_threadsafe(self._apply(cmd), self.loop)

    async def _apply(self, cmd):
        try:
            if "state" in cmd:
                self.state["state"] = cmd["state"]
                if cmd["state"] == "OFF":
                    await self.ball.power(False)
                else:
                    await self.ball.power(True)
            if "brightness" in cmd:
                self.state["brightness"] = cmd["brightness"]
                await self.ball.brightness(cmd["brightness"])
            if "effect" in cmd and cmd["effect"] in EFFECTS:
                self.state["effect"] = cmd["effect"]
                self.state["state"] = "ON"
                await EFFECTS[cmd["effect"]](self.ball)
        except Exception as e:  # noqa: BLE001
            log.error("apply failed: %s", e)
        self.mqtt.publish(STATE_T, json.dumps(self.state), retain=True)

    async def run(self):
        self.loop = asyncio.get_event_loop()
        log.info("connecting to ball...")
        await self.ball.connect()
        host = os.environ.get("MQTT_HOST", "127.0.0.1")
        port = int(os.environ.get("MQTT_PORT", "1883"))
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
