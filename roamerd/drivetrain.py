#!/usr/bin/env python3
"""roamerd drivetrain — talks to the RP2350 fast loop over ttyACM0.

Low-level: drive/stop/estop/reset → Pico. Parses TELEM + EVT lines into shared
state. A simple open-loop timed-motion executor maps goal commands (drive N cm,
rotate N deg) to velocity bursts — upgrade to odometry-closed-loop once the
wheel encoders are wired.
"""
import logging
import math
import threading
import time

log = logging.getLogger("roamerd.drivetrain")

DEV = "/dev/ttyACM0"
BAUD = 115200

state = {
    "connected": False,
    "enc_l": 0, "enc_r": 0,
    "vel_l": 0.0, "vel_r": 0.0,
    "batt_mv": 0, "batt_ma": 0,
    "estop": False,
    "bump_l": False, "bump_r": False,
    "cliff_fl": False, "cliff_fr": False, "cliff_bl": False, "cliff_br": False,
    "wheel_l": False, "wheel_r": False,
    "picked_up": False,
}
_lock = threading.Lock()
_stop = threading.Event()
_ser = None


def _send(line):
    if _ser is not None:
        try:
            _ser.write((line + "\n").encode())
        except Exception:
            pass


def drive(left_cm_s, right_cm_s):
    _send(f"MV {left_cm_s:.2f} {right_cm_s:.2f}")


def stop():
    _send("STOP")


def estop():
    _send("ESTOP")


def reset():
    _send("RESET")


def _handle_line(line):
    p = line.strip().split()
    if not p:
        return
    t = p[0]
    with _lock:
        if t == "TELEM" and len(p) >= 18:
            try:
                state.update(
                    enc_l=int(p[2]), enc_r=int(p[3]),
                    vel_l=float(p[4]), vel_r=float(p[5]),
                    batt_mv=int(p[6]), batt_ma=int(p[7]),
                    estop=p[8] == "1",
                    bump_l=p[9] == "1", bump_r=p[10] == "1",
                    cliff_fl=p[11] == "1", cliff_fr=p[12] == "1",
                    cliff_bl=p[13] == "1", cliff_br=p[14] == "1",
                    wheel_l=p[15] == "1", wheel_r=p[16] == "1",
                    picked_up=p[17] == "1",
                )
            except (ValueError, IndexError):
                pass
        elif t == "EVT":
            log.info("Pico EVT: %s", " ".join(p[1:]))
        elif t in ("PONG", "READY"):
            log.info("Pico: %s", line.strip())
        elif t == "ERR":
            log.warning("Pico ERR: %s", " ".join(p[1:]))


def run():
    import serial
    global _ser
    while not _stop.is_set():
        try:
            _ser = serial.Serial(DEV, BAUD, timeout=0.5)
            with _lock:
                state["connected"] = True
            log.info("drivetrain connected on %s", DEV)
            buf = b""
            while not _stop.is_set():
                buf += _ser.read(512)
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    _handle_line(line.decode(errors="replace"))
        except serial.SerialException as e:
            with _lock:
                state["connected"] = False
            log.warning("drivetrain serial error: %s", e)
        except Exception as e:
            log.warning("drivetrain error: %s", e)
        if not _stop.is_set():
            time.sleep(1.0)


def start():
    threading.Thread(target=run, daemon=True, name="drivetrain").start()


def snapshot():
    with _lock:
        return dict(state)


# --- motion executor (open-loop timed; upgrade to closed-loop later) ---
_TRACK_CM = 15.0  # wheel separation — placeholder, matches config.h TRACK_MM


def _timed(left, right, dur_s):
    drive(left, right)
    time.sleep(dur_s)
    stop()


def drive_for(distance_cm, speed_cm_s):
    if not speed_cm_s:
        return {"status": "error", "error": "speed_cm_s required"}
    v = speed_cm_s if distance_cm >= 0 else -speed_cm_s
    dur = abs(distance_cm) / speed_cm_s
    threading.Thread(target=_timed, args=(v, v, dur), daemon=True).start()
    return {"status": "ok", "note": f"open-loop drive {distance_cm}cm @ {speed_cm_s}cm/s (~{dur:.2f}s)"}


def rotate_for(degrees, direction="cw", speed_cm_s=15.0):
    sign = 1.0 if direction == "cw" else -1.0
    ang_vel = speed_cm_s / (_TRACK_CM / 2.0)   # rad/s
    dur = math.radians(abs(degrees)) / ang_vel
    v = speed_cm_s * sign
    threading.Thread(target=_timed, args=(v, -v, dur), daemon=True).start()
    return {"status": "ok", "note": f"open-loop rotate {degrees}deg {direction} (~{dur:.2f}s)"}
