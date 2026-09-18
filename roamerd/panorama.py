#!/usr/bin/env python3
"""roamerd panorama — 4× UVC cams stitched into one 2×2 image for vision ingestion.

Grid layout (as Sydney specified): TL=forward, TR=back, BL=left, BR=right, with
direction labels burned into each quadrant so the vision model gets explicit
spatial grounding (a CSS overlay would never reach the ingested JPEG bytes).

Hardware note: all 4 cams hang off one Genesys Logic GL850G USB 2.0 hub, which can
only stream TWO concurrent UVC (isochronous) endpoints — a 3rd camera's read() just
fails, regardless of resolution or open order. So we time-multiplex: stream
forward+back, then left+right, alternating. Fine for a static body. For truly
simultaneous 4-cam capture the cameras must be split across two USB controllers.
"""
import io
import logging
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("roamerd.panorama")

# USB hub port → /dev/videoN → label → grid position. Reorder to match physical mounting.
#   usb-xhci-hcd.1-1.1 = /dev/video0   (default: forward)
#   usb-xhci-hcd.1-1.2 = /dev/video8   (default: back)
#   usb-xhci-hcd.1-1.3 = /dev/video12  (default: left)
#   usb-xhci-hcd.1-1.4 = /dev/video14  (default: right)
GROUPS = [
    [("/dev/video0",  "FORWARD", (0, 0)), ("/dev/video8",  "BACK",  (0, 1))],
    [("/dev/video12", "LEFT",    (1, 0)), ("/dev/video14", "RIGHT", (1, 1))],
]
_ALL = [(dev, label, pos) for g in GROUPS for dev, label, pos in g]
TILE_W, TILE_H = 320, 240

_latest = None
_lock = threading.Lock()
_stop = threading.Event()


def _font(size=20):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _open(dev):
    import cv2
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    if cap.isOpened():
        # YUYV-only cams; 320×240 keeps each stream light.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, TILE_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TILE_H)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _encode(canvas):
    img = Image.fromarray(canvas, "RGB")
    draw = ImageDraw.Draw(img)
    font = _font(20)
    for _dev, label, (r, c) in _ALL:
        x = c * TILE_W + 10
        y = r * TILE_H + 8
        draw.text((x, y), label, fill=(255, 255, 255), font=font,
                  stroke_width=2, stroke_fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def run():
    import cv2
    global _latest
    canvas = np.full((TILE_H * 2, TILE_W * 2, 3), 16, dtype=np.uint8)
    gi = 0
    first = True
    while not _stop.is_set():
        try:
            devs = [d for d, _l, _p in GROUPS[gi]]
            poss = [p for _d, _l, p in GROUPS[gi]]
            caps = []
            for d in devs:
                cap = _open(d)
                caps.append(cap if (cap is not None and cap.isOpened()) else None)
            best = {}
            for _ in range(4):  # a few frames so auto-exposure settles
                for pos, cap in zip(poss, caps):
                    if cap is None:
                        continue
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        best[pos] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                time.sleep(0.12)
            for cap in caps:
                if cap is not None:
                    cap.release()
            for pos, rgb in best.items():
                r, c = pos
                canvas[r * TILE_H:(r + 1) * TILE_H, c * TILE_W:(c + 1) * TILE_W] = cv2.resize(rgb, (TILE_W, TILE_H))
            jpeg = _encode(canvas)
            if first:
                log.info("panorama: first frame (%d bytes)", len(jpeg))
                first = False
            with _lock:
                _latest = jpeg
            gi = 1 - gi
        except Exception as e:
            log.warning("panorama error: %s", e)
            time.sleep(0.5)


def start():
    threading.Thread(target=run, daemon=True, name="panorama").start()


def get_frame():
    with _lock:
        return _latest
