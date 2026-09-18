#!/usr/bin/env python3
"""roamerd panorama — 4× UVC cams stitched into one 2×2 image for vision ingestion.

Grid layout (as Sydney specified): TL=forward, TR=back, BL=left, BR=right.

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
from PIL import Image

log = logging.getLogger("roamerd.panorama")

# USB hub port → /dev/videoN → role.  Reorder roles to match physical mounting.
#   usb-xhci-hcd.1-1.1 = /dev/video0   (default: forward)
#   usb-xhci-hcd.1-1.2 = /dev/video8   (default: back)
#   usb-xhci-hcd.1-1.3 = /dev/video12  (default: left)
#   usb-xhci-hcd.1-1.4 = /dev/video14  (default: right)
GROUPS = [
    [("/dev/video0",  (0, 0)), ("/dev/video8",  (0, 1))],   # forward, back
    [("/dev/video12", (1, 0)), ("/dev/video14", (1, 1))],   # left, right
]
TILE_W, TILE_H = 320, 240

_latest = None
_lock = threading.Lock()
_stop = threading.Event()


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
    buf = io.BytesIO()
    Image.fromarray(canvas, "RGB").save(buf, "JPEG", quality=82)
    return buf.getvalue()


def run():
    import cv2
    global _latest
    canvas = np.full((TILE_H * 2, TILE_W * 2, 3), 16, dtype=np.uint8)
    gi = 0
    first = True
    while not _stop.is_set():
        try:
            caps = []
            for dev, _pos in GROUPS[gi]:
                cap = _open(dev)
                caps.append(cap if (cap is not None and cap.isOpened()) else None)
            best = {}
            for _ in range(4):  # a few frames so auto-exposure settles
                for (dev, pos), cap in zip(GROUPS[gi], caps):
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
