#!/usr/bin/env python3
"""roamerd servo — PCA9685 pan/tilt head (16-channel PWM driver over I2C).

The PCA9685's active-low OE line is on Pi GPIO4, so we drive it low to enable
the servos and high to kill them all (a software "servo off" line). Servo angle
convention: 90° = centred/forward (Sydney mounts the head so the cameras point
forward at 50% duty).
"""
import logging
import subprocess
import threading
import time

log = logging.getLogger("roamerd.servo")

I2C_ADDR = 0x40
PAN_CH = 14
TILT_CH = 15
ENABLE_GPIO = 4        # PCA9685 OE (active-low)
FREQ = 50              # servo PWM frequency (Hz)
MIN_PULSE_MS = 1.0     # pulse width @ 0°
MAX_PULSE_MS = 2.0     # pulse width @ 180°

_lock = threading.Lock()
_bus = None
_pan = 90.0
_tilt = 90.0


def _enable(on=True):
    level = "dl" if on else "dh"   # OE active-low: low = enabled
    subprocess.run(["pinctrl", "set", str(ENABLE_GPIO), "op", level],
                   check=False, capture_output=True)


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


def _set_angle(ch, deg):
    deg = max(0.0, min(180.0, float(deg)))
    pulse = MIN_PULSE_MS + (deg / 180.0) * (MAX_PULSE_MS - MIN_PULSE_MS)
    cnt = int(round(pulse / (1000.0 / FREQ) * 4096))
    reg = 0x06 + 4 * ch
    _bus.write_byte_data(I2C_ADDR, reg, 0x00)
    _bus.write_byte_data(I2C_ADDR, reg + 1, 0x00)
    _bus.write_byte_data(I2C_ADDR, reg + 2, cnt & 0xFF)
    _bus.write_byte_data(I2C_ADDR, reg + 3, (cnt >> 8) & 0x0F)


def pan(deg):
    global _pan
    with _lock:
        _set_angle(PAN_CH, deg)
        _pan = deg


def tilt(deg):
    global _tilt
    with _lock:
        _set_angle(TILT_CH, deg)
        _tilt = deg


def look(pan_deg, tilt_deg):
    pan(pan_deg)
    tilt(tilt_deg)


def center():
    look(90.0, 90.0)


def get_state():
    with _lock:
        return {"pan_deg": _pan, "tilt_deg": _tilt}


def start():
    _enable(True)
    _init_bus()
    center()
    log.info("servo: PCA9685 ch %d/%d @ %d Hz, OE=GPIO%d",
             PAN_CH, TILT_CH, FREQ, ENABLE_GPIO)
