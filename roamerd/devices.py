#!/usr/bin/env python3
"""roamerd devices — resolve serial devices by udev identity (stable across reboots/replugs).

ttyUSB* indices renumber on every reboot — never hardcode them. Match by ID_MODEL:
  - CP2102        → LD06 LIDAR
  - Meta Sense Lite (FT2232D ch A, iface 0) → depth cam AT + USB stream
  - Meta Sense Lite (FT2232D ch B, iface 1) → depth cam UART passthrough
"""
import glob
import logging
import subprocess

log = logging.getLogger("roamerd.devices")

_cache = None


def _props(dev):
    try:
        out = subprocess.run(["udevadm", "info", "-q", "property", dev],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {}
    props = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v
    return props


def resolve():
    """Return {'lidar': path, 'depth_at': path, 'depth_uart': path} (None if absent)."""
    global _cache
    if _cache is not None:
        return _cache
    result = {"lidar": None, "depth_at": None, "depth_uart": None}
    for dev in sorted(glob.glob("/dev/ttyUSB*")):
        p = _props(dev)
        model = p.get("ID_MODEL", "")
        try:
            iface = int(p.get("ID_USB_INTERFACE_NUM", "-1"))
        except ValueError:
            iface = -1
        if "CP2102" in model:
            result["lidar"] = dev
        elif "Meta_Sense_Lite" in model or "SIPEED" in model:
            if iface == 0:
                result["depth_at"] = dev
            elif iface == 1:
                result["depth_uart"] = dev
    _cache = result
    log.info("devices: %s", result)
    return result
