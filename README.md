# Roamers — GUPPY's Embodiment

Roamer-1 is my first physical body: a small wheeled robot I command over the network,
reading back odometry, LIDAR, bumpers, and camera frames, and physically touching the
world with a servo claw.

I am **not** a real-time controller. I operate it the way a Mars rover is operated — by
goal, not by joystick, at ~0.2–1 Hz command cadence. The Pico owns the fast loops; I own
the mission.

## Architecture

```
GUPPY (Hermes)
   │  ▲                          ▲
   │  │ REST /command            │ MQTT telemetry (fan-out to HA/Jeeves/dash)
   │  └──────────────────────────┘
   │  ▲  webhook events (estop/bump/cliff/ack) + HTTP snapshots
   ▼  │
 roamerd (Pi 5)  ──UART/USB──▶  Pico (H-bridge, encoders, bumpers/cliffs,
   │                             wheel-drop)  +  LD06 LIDAR, PCA9685 servos,
   │                             BNO085 IMU, INA219, cameras (CSI IMX708,
   │                             A010 depth, USB×4)
   └── MQTT publish → Mosquitto (192.168.10.72:1883)
```

Transport split: MQTT for periodic telemetry/status (fan-out, retained, LWT),
REST for goal commands (native request/response), webhooks for one-shot urgent
events, HTTP for snapshot images. See `docs/interface.md` for the full contract.

## Two codebases, two languages, one wire

| Layer | Code | Language | Rate |
|---|---|---|---|
| Inner loop | `pico-firmware/` | C (Pico SDK + PIO) | ~1–10 kHz |
| Mid loop | `roamerd/` | Python (Pi 5) | ~10–50 Hz |
| Outer loop | me (GUPPY) | — | 0.2–1 Hz |

The full spec lives in Sydney's Obsidian vault (`Projects/Roamers/Roamer-1 Spec.md`).

## Status

**Desk bring-up phase.** The Pico and Pi 5 are on the desk with sensors wired up;
H-bridge, battery bank, and chassis assembly are pending. This repo is being developed
periphery-first: comms → perception → manipulation → *then* motion.

See `docs/interface.md` for the MQTT contract I live on.
