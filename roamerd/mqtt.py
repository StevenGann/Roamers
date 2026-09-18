#!/usr/bin/env python3
"""roamerd MQTT bridge — telemetry, retained status, LWT."""
import json
import logging
import threading
import time

from . import core

log = logging.getLogger("roamerd.mqtt")

try:
    import paho.mqtt.client as mqtt
    _HAVE_MQTT = True
except ImportError:
    _HAVE_MQTT = False
    log.warning("paho-mqtt not installed; MQTT disabled")


def _base(client_id=core.DEVICE_ID):
    c = mqtt.Client(client_id=client_id)
    c.will_set(f"roamer/{core.DEVICE_ID}/status",
               json.dumps({"online": False, "id": core.DEVICE_ID}),
               qos=1, retain=True)
    return c


def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("MQTT connected to %s:%s", core.BROKER_HOST, core.BROKER_PORT)
        client.publish(f"roamer/{core.DEVICE_ID}/status",
                       json.dumps({"online": True, "id": core.DEVICE_ID,
                                   "name": core.NAME, "version": "0.1.0",
                                   "uptime_s": int(time.time() - _start)}),
                       qos=1, retain=True)
        client.publish(f"roamer/{core.DEVICE_ID}/capabilities",
                       json.dumps(core.CAPABILITIES), qos=1, retain=True)
    else:
        log.error("MQTT connect failed rc=%s", rc)


_start = time.time()


def _publisher():
    c = _base()
    c.on_connect = _on_connect
    c.connect(core.BROKER_HOST, core.BROKER_PORT, keepalive=30)
    c.loop_start()
    interval = 1.0 / core.TELEMETRY_HZ
    while True:
        try:
            snap = core.control_snapshot()
            t = dict(core._last_telemetry)
            t["ts"] = int(time.time())
            t["estop"] = snap["estop"]
            c.publish(f"roamer/{core.DEVICE_ID}/telemetry", json.dumps(t), qos=0)
            c.publish(f"roamer/{core.DEVICE_ID}/control",
                      json.dumps({"held": snap["held"], "owner": snap["owner"],
                                  "mode": snap["mode"]}), qos=1, retain=True)
        except Exception as e:
            log.error("MQTT publish error: %s", e)
        time.sleep(interval)


def start():
    if not _HAVE_MQTT:
        return
    t = threading.Thread(target=_publisher, daemon=True, name="mqtt")
    t.start()
    log.info("MQTT bridge started (telemetry %.1f Hz)", core.TELEMETRY_HZ)
