# Roamer Control — arbiter, lease, and fleet

One invariant rules the body: **at any instant, exactly one controller is in charge,
and that fact is always observable and safely mutable.** Everything here hangs off it.

## The control arbiter

Ordered priority; higher preempts lower:

1. **Safety latch** (estop / watchdog / bumper-cliff) — enforced in Pico firmware
   *and* roamerd. Preempts everything; only `reset` clears it.
2. **Admin override** (Sydney) — any time.
3. **Lease-holder** — the owning agent (Guppy for r1) or a borrower.
4. **Active behavior** — code running under the lease-holder's authority.
5. **Idle.**

## The lease (semaphore)

Source of truth is the body itself (single-writer; no distributed-lock races).
MQTT is the read path (discovery); REST is the write path (mutation).

| Endpoint | Purpose |
|---|---|
| `GET /control` | `{held, owner, mode, since, ttl_s}` |
| `POST /control/request` `{agent, reason, ttl_s}` | grant or queue |
| `POST /control/renew` `{agent}` | heartbeat; lease is a TTL that lapses on crash |
| `POST /control/release` `{agent}` | hand back control |
| `POST /control/override` `{admin}` | Sydney, always |

Rules:

- Owner (Guppy for r1) has implicit priority; others request and queue.
- Lease lapses if the holder stops renewing (crash-safe).
- Releasing or lapsing **auto-deactivates the active behavior**.
- `estop` latches until `reset`, and overrides everyone including the owner.

## Capabilities & the fleet roster

Each roamer publishes **retained** MQTT topics; their union is the live fleet roster.
No central registry service — the retained topics *are* the registry.

- `roamer/<id>/status` — identity, version, uptime; LWT flips it to offline.
- `roamer/<id>/control` — who's driving.
- `roamer/<id>/capabilities` — what it's equipped with (changes only on hardware changes).

Discovery = subscribe to `roamer/+/status`, `roamer/+/control`, `roamer/+/capabilities`,
filter by `held:false` + capability match. Identical code path for Guppy, Jeeves, Alfred.

```json
{
  "id": "r1", "name": "roamer-01",
  "locomotion":  {"type": "differential", "max_speed_cm_s": 25},
  "manipulation": {"claw": true, "servo_axes": ["pan", "tilt"]},
  "sensors": {
    "lidar": {"model": "LD06"}, "depth": {"model": "A010", "res": "100x100"},
    "imu": "BNO085", "camera": {"count": 4, "imx708": true},
    "bumpers": true, "cliffs": true, "wheel_drop": true
  }
}
```

## Locked decisions

- r1 owner = Guppy (others borrow via request; Sydney overrides).
- Wire id `rN` ↔ hostname `roamer-0N`; role lives in capabilities, not the id.
- Capability matching: coarse now (`has_claw: true`); fine later if ambiguity appears.
- In-process behaviors (trusted: Guppy + Sydney); escalate to subprocess if third-party code runs.
