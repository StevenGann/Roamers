#!/usr/bin/env python3
"""roamerd entrypoint."""
import logging
import sys
import threading

from . import core
from . import mqtt
from . import snapshot
from . import web


def setup_logging():
    fmt = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt,
                        datefmt="%H:%M:%S",
                        stream=sys.stdout)
    # also write to a file so it survives SSH disconnect
    import pathlib
    logpath = pathlib.Path("/opt/roamers/roamerd.log")
    logpath.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(logpath))
    fh.setFormatter(logging.Formatter(fmt, "%H:%M:%S"))
    logging.getLogger().addHandler(fh)


def main():
    setup_logging()
    log = logging.getLogger("roamerd")
    log.info("=== roamerd starting: %s (%s) ===", core.NAME, core.DEVICE_ID)
    log.info("drivetrain: %s", core.CAPABILITIES["drivetrain"])

    # warm the camera in the background (non-blocking)
    threading.Thread(target=snapshot._cam, daemon=True, name="camera-warm").start()

    mqtt.start()
    web.start()  # blocks


if __name__ == "__main__":
    main()
