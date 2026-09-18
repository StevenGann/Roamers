#!/usr/bin/env python3
"""roamerd depth — MaixSense-A010 TOF depth map (100×100, 8-bit)."""
import io
import logging
import threading
import time

import numpy as np
from PIL import Image

from . import devices

log = logging.getLogger("roamerd.depth")

BAUD = 115200

_latest = None          # PNG bytes
_lock = threading.Lock()
_stop = threading.Event()

# turbo-ish colormap (256×3): low=far (dark blue) → high=near (red)
_ANCHORS = np.array([
    [0.19, 0.07, 0.23], [0.12, 0.28, 0.53], [0.06, 0.52, 0.75],
    [0.08, 0.75, 0.74], [0.28, 0.91, 0.45], [0.84, 0.88, 0.22],
    [0.95, 0.49, 0.13], [0.90, 0.11, 0.14],
])
_LUT = None


def _get_lut():
    global _LUT
    if _LUT is None:
        xs = np.linspace(0.0, 1.0, len(_ANCHORS))
        lut = np.zeros((256, 3), dtype=np.uint8)
        for c in range(3):
            lut[:, c] = (np.interp(np.linspace(0, 1, 256), xs, _ANCHORS[:, c]) * 255).astype(np.uint8)
        _LUT = lut
    return _LUT


def render(img8):
    """img8: H×W uint8; 0xFF = invalid/out-of-range. Returns RGB ndarray."""
    lut = _get_lut()
    valid = img8 != 0xFF
    t = np.clip(1.0 - img8.astype(np.float32) / 255.0, 0.0, 1.0)  # near → 1.0
    rgb = lut[(t * 255.0).astype(np.uint8)].copy()
    rgb[~valid] = (16, 16, 22)
    return rgb


def _to_png(rgb, up=4):
    h, w = rgb.shape[:2]
    img = Image.fromarray(rgb, "RGB").resize((w * up, h * up), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _handle(frame):
    global _latest
    plen = frame[2] | (frame[3] << 8)
    payload = plen - 16
    side = int(round(payload ** 0.5))
    if side * side != payload or side < 1:
        return
    img = np.frombuffer(frame[4 + 16:4 + 16 + payload], dtype=np.uint8).reshape(side, side)
    png = _to_png(render(img))
    if _latest is None:
        log.info("depth: first frame %dx%d", side, side)
    with _lock:
        _latest = png


def run():
    import serial
    dev = devices.resolve()["depth_at"]
    if not dev:
        log.warning("depth: MaixSense-A010 not found on USB")
        return
    while not _stop.is_set():
        try:
            ser = serial.Serial(dev, BAUD, timeout=1.0)

            def at(cmd):
                ser.reset_input_buffer()
                ser.write(cmd.encode() + b"\r")
                time.sleep(0.3)
                ser.read(500)  # drain reply

            at("AT+BINN=1")   # 100×100
            at("AT+DISP=6")   # USB + UART streaming
            at("AT+FPS=10")
            ser.reset_input_buffer()
            log.info("depth cam streaming on %s (DISP=6)", dev)
            buf = bytearray()
            while not _stop.is_set():
                buf.extend(ser.read(4096))
                while len(buf) >= 2:
                    idx = -1
                    for i in range(len(buf) - 1):
                        if buf[i] == 0x00 and buf[i + 1] == 0xFF:
                            idx = i
                            break
                    if idx < 0:
                        buf = buf[-1:]  # header may be split across reads
                        break
                    if idx > 0:
                        del buf[:idx]
                    if len(buf) < 4:
                        break
                    plen = buf[2] | (buf[3] << 8)
                    if plen < 16:
                        del buf[0]
                        continue
                    total = 4 + plen + 2  # hdr+len + payload + checksum + terminator
                    if len(buf) < total:
                        break
                    frame = bytes(buf[:total])
                    del buf[:total]
                    if frame[-1] == 0xDD:
                        _handle(frame)
        except serial.SerialException as e:
            log.warning("depth serial error: %s", e)
        except Exception as e:
            log.warning("depth error: %s", e)
        if not _stop.is_set():
            time.sleep(1.0)


def start():
    threading.Thread(target=run, daemon=True, name="depth").start()


def get_frame():
    with _lock:
        return _latest
