#!/usr/bin/env python3
"""roamerd snapshot — capture a JPEG from the Arducam IMX708."""
import io
import logging
import threading

log = logging.getLogger("roamerd.snapshot")

_picam = None
_lock = threading.Lock()


def _cam():
    global _picam
    if _picam is not None:
        return _picam
    try:
        from picamera2 import Picamera2
        _picam = Picamera2()
        _picam.configure(_picam.create_still_configuration())
        _picam.start()
        log.info("Arducam IMX708 ready")
    except Exception as e:
        log.warning("camera unavailable: %s", e)
        _picam = False
    return _picam


def capture():
    with _lock:
        cam = _cam()
        if not cam:
            return None
        try:
            buf = io.BytesIO()
            cam.capture_file(buf, format="jpeg")
            return buf.getvalue()
        except Exception as e:
            log.error("capture failed: %s", e)
            return None
