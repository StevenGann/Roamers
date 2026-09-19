#!/usr/bin/env python3
"""roamerd HTTP API + web UI + sensor images."""
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import core
from . import depth
from . import lidar
from . import panorama
from . import slam
from . import servo
from . import snapshot as snap

log = logging.getLogger("roamerd.web")
WEB_DIR = Path(__file__).parent / "web"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("%s %s", self.command, self.path)

    def _send_json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _serve_bytes(self, data, ctype):
        if data is None:
            return self._send_json({"error": "sensor not ready"}, 503)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            return self._serve_file(WEB_DIR / "index.html", "text/html")
        if self.path == "/state":
            s = core.control_snapshot()
            return self._send_json({"owner": s["owner"], "mode": s["mode"],
                                    "held": s["held"], "estop": s["estop"],
                                    "active_behavior": s["active_behavior"],
                                    "telemetry": core.telemetry()})
        if self.path == "/health":
            return self._send_json({"ok": True, "id": core.DEVICE_ID, "name": core.NAME})
        if self.path.startswith("/snapshot"):
            return self._serve_bytes(snap.capture(), "image/jpeg")
        if self.path.startswith("/depth"):
            return self._serve_bytes(depth.get_frame(), "image/png")
        if self.path.startswith("/panorama"):
            return self._serve_bytes(panorama.get_frame(), "image/jpeg")
        if self.path.startswith("/lidar"):
            return self._serve_bytes(lidar.get_frame(), "image/png")
        if self.path.startswith("/slam"):
            return self._serve_bytes(slam.get_map(), "image/png")
        if self.path == "/pose":
            return self._send_json({"pose": slam.get_pose().tolist()})
        if self.path.startswith("/servo"):
            return self._send_json(servo.get_state())
        return self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        body = self._read_body()
        if self.path == "/command":
            return self._send_json(core.handle_command(body))
        if self.path == "/control/request":
            return self._send_json(core.request_control(body.get("agent", "guppy"),
                                                        body.get("reason", ""),
                                                        body.get("ttl_s", 300.0)))
        if self.path == "/control/release":
            return self._send_json(core.release_control(body.get("agent", "guppy")))
        if self.path == "/control/renew":
            return self._send_json(core.renew_control(body.get("agent", "guppy")))
        if self.path == "/control/override":
            return self._send_json(core.override_control(body.get("agent", "sydney")))
        if self.path.startswith("/servo"):
            if "sweep" in body:
                servo.sweep(body["sweep"])
            else:
                servo.look(body.get("pan_deg", 90), body.get("tilt_deg", 90))
            return self._send_json(servo.get_state())
        return self._send_json({"error": "not found"}, 404)

    def _serve_file(self, path, ctype):
        if not path.exists():
            return self._send_json({"error": "not found"}, 404)
        return self._serve_bytes(path.read_bytes(), ctype)


def start():
    srv = ThreadingHTTPServer((core.WEB_HOST, core.WEB_PORT), Handler)
    log.info("web UI + API on http://%s:%s", core.WEB_HOST, core.WEB_PORT)
    srv.serve_forever()
