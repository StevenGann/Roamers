#!/usr/bin/env python3
"""roamerd HTTP API + web UI + snapshot."""
import io
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import core
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
            snap2 = core.control_snapshot()
            return self._send_json({"owner": snap2["owner"], "mode": snap2["mode"],
                                    "held": snap2["held"], "estop": snap2["estop"],
                                    "active_behavior": snap2["active_behavior"],
                                    "telemetry": core._last_telemetry})
        if self.path == "/health":
            return self._send_json({"ok": True, "id": core.DEVICE_ID, "name": core.NAME})
        if self.path.startswith("/snapshot"):
            img = snap.capture()
            if img is None:
                return self._send_json({"error": "no camera"}, 503)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(img)))
            self.end_headers()
            self.wfile.write(img)
            return
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
        return self._send_json({"error": "not found"}, 404)

    def _serve_file(self, path, ctype):
        if not path.exists():
            return self._send_json({"error": "not found"}, 404)
        b = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def start():
    srv = ThreadingHTTPServer((core.WEB_HOST, core.WEB_PORT), Handler)
    log.info("web UI + API on http://%s:%s", core.WEB_HOST, core.WEB_PORT)
    srv.serve_forever()
