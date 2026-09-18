# Roamer-1 Interface — how GUPPY talks to its body

This is the contract between me (GUPPY, the outer loop) and the roamer. It is the
single source of truth for how I command the robot and how it reports back. Every
change to this file is a change to my body's nervous system — treat it as an API.

## Transport split (three channels, each on its natural tool)

| Channel | Transport | Direction | What it carries | Why |
|---|---|---|---|---|
| Telemetry | MQTT | roamer → GUPPY | Periodic state (2 Hz) | Fan-out: me, HA, Jeeves, dashboard all subscribe. Retained status + LWT = "is my body alive?" |
| Commands | REST (HTTP) | GUPPY → roamer | Goal commands | Native request/response, status codes, error bodies |
| Events | Webhook (HTTP POST) | roamer → GUPPY | One-shot urgent: estop, bump, cliff, wheel-drop, ack | Urgent pushes, no polling, no queueing |
| Snapshots | HTTP GET | GUPPY ← roamer | JPEG images on demand | Media bytes stay off the message bus |

## Broker & endpoints

- MQTT broker: `192.168.10.72:1883` (existing homelab Mosquitto). Device id `r1`.
- REST/webhook/snapshot host: `roamerd` on the Pi, HTTP `:8080`.
- Webhook receiver: GUPPY's webhook endpoint (configured in roamerd at deploy time).

## Topics (MQTT — telemetry/status only)

| Topic | Direction | Purpose |
|---|---|---|
| `roamer/r1/telemetry` | roamer → GUPPY | Periodic state (2 Hz) |
| `roamer/r1/status` | roamer → GUPPY (retained) | Heartbeat, version, uptime, LWT offline |

## Commands (REST — goals, not raw PWM)

`POST /command` with a JSON body:

```json
{"id":"...", "type":"drive",   "distance_cm":40, "speed_cm_s":20, "timeout_s":30}
{"id":"...", "type":"rotate",  "degrees":90, "direction":"cw", "timeout_s":15}
{"id":"...", "type":"drive_arc","velocity_cm_s":15, "radius_cm":30, "timeout_s":20}
{"id":"...", "type":"stop"}
{"id":"...", "type":"look_at", "pan_deg":0, "tilt_deg":-20}
{"id":"...", "type":"grab"}
{"id":"...", "type":"release"}
{"id":"...", "type":"scan"}
{"id":"...", "type":"snapshot"}
{"id":"...", "type":"estop"}
{"id":"...", "type":"reset"}
```

Response: HTTP status + JSON `{"id":"...","status":"ok|error","error":"..."}`.
A motion command's completion result arrives as a webhook event: `reached`,
`aborted:bumper`, `aborted:cliff`, `aborted:timeout`, or `aborted:over_error` —
so I know *why* it stopped before I decide the next move.

Every motion command carries a `timeout_s`; the mid loop also aborts on
bumper/cliff/over-error. `tuning` (PID gains, speed/accel/servo limits) is applied
live via `POST /tuning` with a JSON object of key/value overrides.

## Events (webhook POST — one-shot, urgent)

```json
{"type":"ack",        "id":"...", "status":"ok|error", "error":"..."}
{"type":"bump",       "side":"left|right"}
{"type":"cliff",      "side":"fl|fr|bl|br"}
{"type":"wheel_drop", "side":"left|right"}
{"type":"estop",      "source":"auto|command"}
{"type":"low_battery","voltage":11.2, "percent":20}
```

## Snapshots (HTTP GET)

`POST /command {"type":"snapshot"}` → roamerd captures, saves to disk, and replies
with `{"id":"...","status":"ok","url":"http://<pi>:<port>/captures/xxxxx.jpg"}`.
GUPPY then `GET`s the URL. No base64 on the bus, no broker message-size limits.

### Live sensor images (HTTP GET — web UI + vision-model ingestion)

| Endpoint | Source | Format | Notes |
|---|---|---|---|
| `GET /snapshot` | Arducam IMX708 | JPEG | 12 MP still, on demand |
| `GET /panorama` | 4× UVC cams | JPEG | 2×2 stitch: TL=forward, TR=back, BL=left, BR=right (~2 Hz). One image = all four viewpoints for single-call vision ingestion |
| `GET /depth` | MaixSense-A010 TOF | PNG | 100×100 colorized (red=near, blue=far, dark=no-return) |
| `GET /lidar` | LD06 | PNG | top-down scan, robot at centre, ~6 m view |

## Telemetry (2 Hz)

```json
{
  "ts": 1750000000,
  "odometry": {"x_cm": 0.0, "y_cm": 0.0, "heading_deg": 0.0},
  "imu":      {"heading_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0, "picked_up": false},
  "battery":  {"voltage": 12.0, "current_a": 0.5, "percent": 82},
  "bumpers":  {"left": false, "right": false},
  "cliffs":   {"fl": false, "fr": false, "bl": false, "br": false},
  "wheel_drop": {"left": false, "right": false},
  "servos":   {"pan_deg": 0, "tilt_deg": -20, "claw": "open"},
  "estop":    false
}
```

## Safety invariants (must never regress)

- Bumper / cliff / wheel-drop stop is enforced in **Pico firmware**, independent of Pi and of me.
- Watchdog: no command/heartbeat within 5 s → `roamerd` issues `stop`.
- `estop` latches until explicit `reset`.
- Speed cap ≤ 25 cm/s.
- Camera capture only on `snapshot` or explicit `stream on`.
