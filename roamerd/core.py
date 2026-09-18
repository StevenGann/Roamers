#!/usr/bin/env python3
"""roamerd — the mid-loop for Roamer-01. Terminal logging + web UI + control arbiter + MQTT telemetry."""
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

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


def control_snapshot():
    with _state_lock:
        s = dict(state)
        s["since"] = s["since"]
        return s


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
        log.warning("ESTOP %s", "LATCHED" if on else "cleared")
        return {"ok": True, "estop": on}


def handle_command(cmd):
    """Goal commands. Motion returns 'no drivetrain' until H-bridge is assembled."""
    t = cmd.get("type")
    log.info("command received: %s", json.dumps(cmd, default=str))
    if state["estop"] and t not in ("reset", "estop"):
        return {"status": "error", "error": "estop latched"}
    if t == "estop":
        return set_estop(True)
    if t == "reset":
        return set_estop(False)
    if t in ("drive", "rotate", "drive_arc", "stop", "look_at", "grab", "release", "scan"):
        return {"status": "ok", "note": "no drivetrain/actuators yet (pending hardware)"}
    if t == "snapshot":
        return {"status": "ok", "url": f"http://{NAME}.local:{WEB_PORT}/snapshot"}
    return {"status": "error", "error": "unknown command type: " + str(t)}
