#!/usr/bin/env python3
"""roamerd — the mid-loop for Roamer-01. Terminal logging + web UI + control arbiter + MQTT telemetry."""
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

from . import drivetrain
from . import servo

# --- config ---
DEVICE_ID = "r1"
NAME = "roamer-01"
BROKER_HOST = "192.168.10.72"
BROKER_PORT = 1883
# Credentials come from a gitignored secrets file (this repo is public).
_secrets = {}
_secrets_path = Path(__file__).parent / ".mqtt-secrets"
if _secrets_path.exists():
    import configparser
    _cp = configparser.ConfigParser()
    _cp.read(_secrets_path)
    _secrets = dict(_cp["mqtt"]) if _cp.has_section("mqtt") else {}
BROKER_USER = _secrets.get("user", os.environ.get("ROAMER_MQTT_USER", ""))
BROKER_PASS = _secrets.get("password", os.environ.get("ROAMER_MQTT_PASS", ""))
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080
TELEMETRY_HZ = 2.0

log = logging.getLogger("roamerd")

# --- control state (the arbiter) ---
_state_lock = threading.Lock()
state = {
    "held": False,
    "owner": None,
    "mode": "idle",
    "since": None,
    "ttl_s": 300.0,
    "reason": "",
    "estop": False,
    "active_behavior": None,
    "behaviors": {},
}
_last_telemetry = {
    "ts": 0, "odometry": {"x_cm": 0, "y_cm": 0, "heading_deg": 0},
    "imu": {"heading_deg": 0, "pitch_deg": 0, "roll_deg": 0, "picked_up": False},
    "battery": {"voltage": 12.0, "current_a": 0.0, "percent": 100},
    "bumpers": {"left": False, "right": False},
    "cliffs": {"fl": False, "fr": False, "bl": False, "br": False},
    "wheel_drop": {"left": False, "right": False},
    "servos": {"pan_deg": 0, "tilt_deg": -20, "claw": "open"},
    "estop": False,
}

CAPABILITIES = {
    "id": DEVICE_ID, "name": NAME,
    "locomotion": {"type": "differential", "max_speed_cm_s": 25, "available": False},
    "manipulation": {"claw": True, "servo_axes": ["pan", "tilt"], "available": False},
    "sensors": {
        "lidar": {"model": "LD06"}, "depth": {"model": "A010", "res": "100x100"},
        "imu": "BNO085", "camera": {"count": 4, "imx708": True},
        "bumpers": True, "cliffs": True, "wheel_drop": True,
    },
    "drivetrain": "pending",  # H-bridge + battery not yet assembled
}


def _now():
    return int(time.time())


def _battery_percent(mv):
    lo, hi = 9000.0, 12600.0  # 3S LiPo-ish: 9.0V = 0%, 12.6V = 100%
    if mv <= lo:
        return 0
    if mv >= hi:
        return 100
    return int(round((mv - lo) / (hi - lo) * 100))


def telemetry():
    """Merge live drivetrain state into the telemetry payload."""
    d = drivetrain.snapshot()
    t = json.loads(json.dumps(_last_telemetry))
    t["battery"]["voltage"] = round(d["batt_mv"] / 1000.0, 2)
    t["battery"]["current_a"] = round(d["batt_ma"] / 1000.0, 2)
    t["battery"]["percent"] = _battery_percent(d["batt_mv"])
    t["bumpers"]["left"] = d["bump_l"]
    t["bumpers"]["right"] = d["bump_r"]
    t["cliffs"]["fl"] = d["cliff_fl"]
    t["cliffs"]["fr"] = d["cliff_fr"]
    t["cliffs"]["bl"] = d["cliff_bl"]
    t["cliffs"]["br"] = d["cliff_br"]
    t["wheel_drop"]["left"] = d["wheel_l"]
    t["wheel_drop"]["right"] = d["wheel_r"]
    t["estop"] = d["estop"] or t["estop"]
    t["imu"]["picked_up"] = d["picked_up"]
    t["drivetrain"] = {"connected": d["connected"], "vel_l_cm_s": d["vel_l"],
                       "vel_r_cm_s": d["vel_r"], "enc_l": d["enc_l"], "enc_r": d["enc_r"]}
    s = servo.get_state()
    t["servos"]["pan_deg"] = s["pan_deg"]
    t["servos"]["tilt_deg"] = s["tilt_deg"]
    return t


def control_snapshot():
    with _state_lock:
        return dict(state)


def request_control(agent, reason="", ttl_s=300.0):
    with _state_lock:
        if state["estop"]:
            return {"granted": False, "error": "estop latched; reset first"}
        if state["held"] and state["owner"] != agent:
            return {"granted": False, "queued": True, "owner": state["owner"]}
        state.update(held=True, owner=agent, mode="lease", since=_now(),
                     ttl_s=ttl_s, reason=reason)
        log.info("control granted to %s (reason=%r)", agent, reason)
        return {"granted": True, "owner": agent}


def renew_control(agent):
    with _state_lock:
        if not state["held"] or state["owner"] != agent:
            return {"ok": False, "error": "not held by " + str(agent)}
        state["since"] = _now()
        return {"ok": True}


def release_control(agent):
    with _state_lock:
        if state["held"] and state["owner"] == agent:
            state.update(held=False, owner=None, mode="idle", since=None,
                         active_behavior=None)
            log.info("control released by %s", agent)
            return {"ok": True}
        return {"ok": False, "error": "not held by " + str(agent)}


def override_control(agent):
    """Admin override — Sydney."""
    with _state_lock:
        state.update(held=True, owner=agent, mode="admin", since=_now(),
                     active_behavior=None)
        log.warning("ADMIN OVERRIDE by %s", agent)
        return {"ok": True, "owner": agent}


def set_estop(on=True):
    with _state_lock:
        state["estop"] = on
        if on:
            state["active_behavior"] = None
    if on:
        drivetrain.estop()
    else:
        drivetrain.reset()
    log.warning("ESTOP %s", "LATCHED" if on else "cleared")
    return {"ok": True, "estop": on}


def handle_command(cmd):
    """Goal commands, translated to drivetrain/Pico actions."""
    t = cmd.get("type")
    log.info("command received: %s", json.dumps(cmd, default=str))
    if state["estop"] and t not in ("reset", "estop"):
        return {"status": "error", "error": "estop latched"}
    if t == "estop":
        return set_estop(True)
    if t == "reset":
        return set_estop(False)
    if t == "drive":
        return drivetrain.drive_for(cmd.get("distance_cm", 0), cmd.get("speed_cm_s", 20))
    if t == "rotate":
        return drivetrain.rotate_for(cmd.get("degrees", 90), cmd.get("direction", "cw"),
                                     cmd.get("speed_cm_s", 15.0))
    if t == "stop":
        drivetrain.stop()
        return {"status": "ok"}
    if t == "look_at":
        pan_deg = cmd.get("pan_deg", 90)
        tilt_deg = cmd.get("tilt_deg", 90)
        servo.look(pan_deg, tilt_deg)
        return {"status": "ok", "pan_deg": pan_deg, "tilt_deg": tilt_deg}
    if t in ("drive_arc", "grab", "release", "scan"):
        return {"status": "ok", "note": "not yet implemented"}
    if t == "snapshot":
        return {"status": "ok", "url": f"http://{NAME}.local:{WEB_PORT}/snapshot"}
    return {"status": "error", "error": "unknown command type: " + str(t)}
