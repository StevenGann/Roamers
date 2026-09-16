# Roamer-1 Interface — the MQTT contract GUPPY lives on

This is the contract between me (GUPPY, the outer loop) and the roamer. It is the
single source of truth for how I command the robot and how it reports back. Every
change to this file is a change to my body's nervous system — treat it as an API.

Broker: `192.168.10.72:1883` (existing homelab Mosquitto). Device id `r1`.

## Topics

| Topic | Direction | Purpose |
|---|---|---|
| `roamer/r1/command` | GUPPY → roamer | JSON command |
| `roamer/r1/telemetry` | roamer → GUPPY | Periodic state (2 Hz) |
| `roamer/r1/event` | roamer → GUPPY | One-shot: bump, cliff, e-stop, low battery, ack |
| `roamer/r1/camera/snapshot` | roamer → GUPPY | Base64 JPEG on demand (≤1 Hz) |
| `roamer/r1/tuning` | GUPPY → roamer | PID gains, speed/accel limits, servo limits |
| `roamer/r1/status` | roamer → GUPPY (retained) | Heartbeat, version, uptime |

## Commands (goals, not raw PWM)

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

Every motion command carries a `timeout_s`; the mid loop also aborts on
bumper/cliff/over-error. `tuning` is a JSON object of key/value overrides applied live.

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

## Command ack

Every command gets an `event` ack: `{"type":"ack","id":"…","status":"ok|error","error":"…"}`.
A motion command's ack reports the completion result — `reached`, `aborted:bumper`,
`aborted:cliff`, `aborted:timeout`, or `aborted:over_error` — so I know *why* it stopped
before I decide the next move.

## Safety invariants (must never regress)

- Bumper / cliff / wheel-drop stop is enforced in **Pico firmware**, independent of Pi and of me.
- Watchdog: no command/heartbeat within 5 s → `roamerd` issues `stop`.
- `estop` latches until explicit `reset`.
- Speed cap ≤ 25 cm/s.
- Camera capture only on `snapshot` or explicit `stream on`.
