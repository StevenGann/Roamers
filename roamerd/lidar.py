#!/usr/bin/env python3
"""roamerd lidar — LD06 2D LIDAR top-down visualization (radar-style)."""
import io
import logging
import math
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import devices

log = logging.getLogger("roamerd.lidar")

BAUD = 230400
SIZE = 480             # px (square)
SCALE = 80.0           # px per metre → ~6 m view
MAX_RANGE_M = 5.9

_latest = None
_lock = threading.Lock()
_stop = threading.Event()
_bins = np.full(360, np.nan)   # distance (m) per 1° bin


def _font(size=11):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _parse_packet(pkt):
    if len(pkt) != 47 or pkt[0] != 0x54 or pkt[1] != 0x2C:
        return None
    start = (pkt[4] | (pkt[5] << 8)) / 100.0
    end = (pkt[42] | (pkt[43] << 8)) / 100.0   # end angle at offset 42-43, NOT 38
    if end < start:
        end += 360.0  # angle wraps across 0°/360°
    step = (end - start) / 11.0
    pts = []
    for i in range(12):
        off = 6 + i * 3
        dist_mm = pkt[off] | (pkt[off + 1] << 8)
        conf = pkt[off + 2]
        if dist_mm > 0 and conf > 0:
            pts.append((start + step * i, dist_mm / 1000.0))
    return pts


def _render():
    img = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    img[:] = (12, 14, 20)
    cx = cy = SIZE // 2
    # scan points (0° = up = forward)
    for a_deg in range(360):
        d = _bins[a_deg]
        if not np.isfinite(d) or d <= 0:
            continue
        r = math.radians(a_deg)
        px = cx + d * SCALE * math.sin(r)
        py = cy - d * SCALE * math.cos(r)
        if 0 <= px < SIZE and 0 <= py < SIZE:
            t = min(max(d / MAX_RANGE_M, 0.0), 1.0)
            img[int(py), int(px)] = (int(255 * (1 - t)), int(110 * (1 - t)), int(40 + 215 * t))
    # --- radar overlay ---
    pil = Image.fromarray(img, "RGB")
    draw = ImageDraw.Draw(pil)
    font = _font(11)
    grid = (58, 70, 92)      # faint blue-gray
    fwd = (0, 190, 255)      # cyan forward accent
    lab = (110, 122, 140)    # distance-label gray
    # range rings every 1 m
    for m in range(1, 6):
        rpx = int(m * SCALE)
        if rpx < SIZE // 2:
            draw.ellipse([cx - rpx, cy - rpx, cx + rpx, cy + rpx], outline=grid, width=1)
    # crosshair N/S/E/W
    draw.line([(cx, 0), (cx, SIZE)], fill=grid, width=1)
    draw.line([(0, cy), (SIZE, cy)], fill=grid, width=1)
    # forward arrow (up) + label
    draw.polygon([(cx - 6, 22), (cx + 6, 22), (cx, 6)], fill=fwd)
    draw.text((cx + 10, 8), "FWD", fill=fwd, font=font, stroke_width=1, stroke_fill=(0, 0, 0))
    # distance labels along the forward axis
    for m in range(1, 6):
        draw.text((cx + 4, cy - m * SCALE + 2), f"{m}m", fill=lab, font=font)
    # robot marker (white square) on top
    draw.rectangle([cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5], fill=(255, 255, 255))
    buf = io.BytesIO()
    pil.save(buf, "PNG")
    return buf.getvalue()


def run():
    import serial
    global _latest
    dev = devices.resolve()["lidar"]
    if not dev:
        log.warning("lidar: LD06 not found on USB")
        return
    while not _stop.is_set():
        try:
            ser = serial.Serial(dev, BAUD, timeout=0.5)
            log.info("lidar on %s @ %d", dev, BAUD)
            buf = bytearray()
            last = 0.0
            while not _stop.is_set():
                buf.extend(ser.read(512))
                while len(buf) >= 47:
                    if buf[0] != 0x54:
                        del buf[0]
                        continue
                    pkt = bytes(buf[:47])
                    del buf[:47]
                    pts = _parse_packet(pkt)
                    if pts:
                        for a, d in pts:
                            _bins[int(a) % 360] = d
                now = time.time()
                if now - last > 0.15:
                    last = now
                    png = _render()
                    if _latest is None:
                        log.info("lidar: first frame (%d bytes)", len(png))
                    with _lock:
                        _latest = png
        except serial.SerialException as e:
            log.warning("lidar serial error: %s", e)
        except Exception as e:
            log.warning("lidar error: %s", e)
        if not _stop.is_set():
            time.sleep(1.0)


def start():
    threading.Thread(target=run, daemon=True, name="lidar").start()


def get_frame():
    with _lock:
        return _latest
