#!/usr/bin/env python3
"""roamerd servo — PCA9685 pan/tilt head (16-channel PWM driver over I2C).

The PCA9685's active-low OE line is on Pi GPIO4: driven LOW = enabled, HIGH =
all outputs killed (a software "servo off" line).

Calibration config (all in one place — tune on the bench):
  PAN_CH / TILT_CH   which PCA9685 channel each servo is on
  PAN_DIR / TILT_DIR +1 or -1 to flip which physical side ">90°" points to
  90° = centred/forward (Sydney mounts the head at 50% duty).
"""
import logging
import subprocess
import threading
import time

log = logging.getLogger("roamerd.servo")

I2C_ADDR = 0x40
PAN_CH = 14            # pan  (side-to-side)
TILT_CH = 15           # tilt (up-down)
PAN_DIR = 1            # +1: pan_deg > 90 turns LEFT;  -1: RIGHT
TILT_DIR = 1           # +1: tilt_deg > 90 pitches UP; -1: DOWN
ENABLE_GPIO = 4        # PCA9685 OE (active-low)
FREQ = 50              # servo PWM frequency (Hz)
MIN_PULSE_MS = 1.0     # pulse width @ 0°
MAX_PULSE_MS = 2.0     # pulse width @ 180°
CENTER_DEG = 90.0      # "forward/level"

_lock = threading.Lock()
_bus = None
_pan = 90.0
_tilt = 90.0


def _enable(on=True):
    level = "dl" if on else "dh"   # OE active-low: low = enabled
    r = subprocess.run(["pinctrl", "set", str(ENABLE_GPIO), "op", level],
                       check=False, capture_output=True, text=True)
    if r.returncode != 0:
        log.warning("servo: pinctrl enable failed: %s", (r.stderr or "").strip())


def _init_bus():
    global _bus
    import smbus2
    _bus = smbus2.SMBus(1)
    try:
        _bus.write_byte(0x00, 0x06)          # software reset (general call)
    except Exception:
        pass
    time.sleep(0.02)
    _bus.write_byte_data(I2C_ADDR, 0x00, 0x00); time.sleep(0.02)
    _bus.write_byte_data(I2C_ADDR, 0x00, 0x10)          # sleep
    ps = int(round(25000000.0 / (4096.0 * FREQ)) - 1)
    _bus.write_byte_data(I2C_ADDR, 0xFE, ps)
    _bus.write_byte_data(I2C_ADDR, 0x00, 0x00); time.sleep(0.02)
    _bus.write_byte_data(I2C_ADDR, 0x00, 0x80)          # restart


def _set_raw(ch, raw_deg):
    raw_deg = max(0.0, min(180.0, float(raw_deg)))
    pulse = MIN_PULSE_MS + (raw_deg / 180.0) * (MAX_PULSE_MS - MIN_PULSE_MS)
    cnt = int(round(pulse / (1000.0 / FREQ) * 4096))
    reg = 0x06 + 4 * ch
    _bus.write_byte_data(I2C_ADDR, reg, 0x00)
    _bus.write_byte_data(I2C_ADDR, reg + 1, 0x00)
    _bus.write_byte_data(I2C_ADDR, reg + 2, cnt & 0xFF)
    _bus.write_byte_data(I2C_ADDR, reg + 3, (cnt >> 8) & 0x0F)


def _logical_to_raw(logical_deg, direction):
    return CENTER_DEG + direction * (logical_deg - CENTER_DEG)


def pan(logical_deg):
    global _pan
    with _lock:
        _set_raw(PAN_CH, _logical_to_raw(logical_deg, PAN_DIR))
        _pan = logical_deg


def tilt(logical_deg):
    global _tilt
    with _lock:
        _set_raw(TILT_CH, _logical_to_raw(logical_deg, TILT_DIR))
        _tilt = logical_deg


def look(pan_deg, tilt_deg):
    pan(pan_deg)
    tilt(tilt_deg)


def center():
    look(CENTER_DEG, CENTER_DEG)


def sweep(ch, lo=30.0, hi=150.0, hold=0.8):
    """Calibration: move one channel lo -> hi -> centre, holding at each."""
    for a in (lo, hi, CENTER_DEG):
        _set_raw(ch, a)
        time.sleep(hold)


def get_state():
    with _lock:
        return {"pan_deg": _pan, "tilt_deg": _tilt}


def start():
    _enable(True)
    _init_bus()
    center()
    log.info("servo: PCA9685 pan=ch%d tilt=ch%d @ %d Hz, OE=GPIO%d, dir=(%+d,%+d)",
             PAN_CH, TILT_CH, FREQ, ENABLE_GPIO, PAN_DIR, TILT_DIR)
