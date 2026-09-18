#!/usr/bin/env python3
"""roamerd panorama — 4× UVC cams stitched into one 2×2 image for vision ingestion.

Grid layout (as Sydney specified): TL=forward, TR=back, BL=left, BR=right.
One JPEG → the vision model ingests all four viewpoints in a single call.
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
CAMERAS = [
    ("/dev/video0",  "forward"),
    ("/dev/video8",  "back"),
    ("/dev/video12", "left"),
    ("/dev/video14", "right"),
]
TILE_W, TILE_H = 320, 240
FPS = 2.0

_latest = None
_lock = threading.Lock()
_stop = threading.Event()


def _open(dev):
    import cv2
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    if cap.isOpened():
        # These Alcor Micro cams are YUYV-only (no MJPG) at 30 fps. 4× 640×480
        # uncompressed saturates USB 2.0 bandwidth → only 2 would capture. 320×240
        # keeps 4 simultaneous streams within budget (18 MB/s total).
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def run():
    import cv2
    global _latest
    caps = []
    for dev, role in CAMERAS:
        cap = _open(dev)
        if not cap.isOpened():
            log.warning("panorama: cannot open %s (%s)", dev, role)
        caps.append((dev, role, cap))

    try:
        while not _stop.is_set():
            tiles = []
            for dev, role, cap in caps:
                if cap is None or not cap.isOpened():
                    tiles.append(None)
                    continue
                ret, frame = cap.read()
                if not ret:
                    tiles.append(None)
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                tiles.append(cv2.resize(rgb, (TILE_W, TILE_H)))
            # 2×2 canvas: TL,TR / BL,BR
            canvas = np.full((TILE_H * 2, TILE_W * 2, 3), 16, dtype=np.uint8)
            for i, (r, c) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1)]):
                if tiles[i] is not None:
                    canvas[r * TILE_H:(r + 1) * TILE_H, c * TILE_W:(c + 1) * TILE_W] = tiles[i]
            img = Image.fromarray(canvas, "RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82)
            jpeg = buf.getvalue()
            if _latest is None:
                log.info("panorama: first frame (%d bytes)", len(jpeg))
            with _lock:
                _latest = jpeg
            time.sleep(1.0 / FPS)
    except Exception as e:
        log.warning("panorama error: %s", e)
    finally:
        for _, _, cap in caps:
            if cap is not None:
                cap.release()


def start():
    threading.Thread(target=run, daemon=True, name="panorama").start()


def get_frame():
    with _lock:
        return _latest
