# Pico ↔ Pi serial protocol

The contract between the RP2350-Zero (fast loop) and `roamerd` (mid loop). The Pico
owns everything that must react in milliseconds and cannot depend on the Pi or on
GUPPY: motor velocity PID, encoder counting, and the bumper/cliff/wheel-drop safety
stop. The Pi sends *goal* velocities; the Pico sends *state*.

## Transport

- USB CDC serial (`/dev/ttyACM0` on the Pi), 115200 baud, 8N1.
- Line-oriented ASCII, `\n`-terminated, so it is trivially debuggable from a terminal.
- All numbers are ASCII; floats in cm/s, ints in raw units.

## Pi → Pico (commands)

One command per line:

| Line | Meaning |
|---|---|
| `MV <L> <R>` | Set wheel velocity targets in cm/s (L=left, R=right). Positive = forward. |
| `STOP` | Coast — motors float. |
| `BRAKE` | Active brake — both motors shorted to stop quickly. |
| `ESTOP` | Latch emergency stop. Motors disabled until `RESET`. |
| `RESET` | Clear the estop latch and re-enable motors. |
| `CONFIG <k> <v>` | Set a config key (see below). |
| `PING` | Reply `PONG <version> <uptime_ms>`. |

Config keys: `KP`, `KI`, `KD` (velocity PID), `ENC_CPR` (encoder counts/rev),
`WHEEL_DIAM_MM`, `TRACK_MM` (wheel separation), `MAX_PWM`.

## Pico → Pi (state)

Telemetry, ~20 Hz, one line:

```
TELEM <ts_ms> <enc_l> <enc_r> <vel_l_cm_s> <vel_r_cm_s> <batt_mv> <batt_ma> <estop> <bump_l> <bump_r> <cliff_fl> <cliff_fr> <cliff_bl> <cliff_br> <wheel_l> <wheel_r> <picked_up>
```

Async events, sent once on state change:

```
EVT BUMP <l|r>
EVT CLIFF <fl|fr|bl|br>
EVT WHEEL_DROP <l|r>
EVT ESTOP <auto|cmd>
EVT PICKED_UP <0|1>
```

Booleans are `0`/`1`.

## Safety model

- **Safety stop** (bumper / cliff / wheel-drop): while moving, the Pico brakes
  autonomously and emits the `EVT`. It does *not* latch — the Pi (or an active
  behavior) decides the recovery. This is enforced in firmware, independent of the
  Pi and of GUPPY.
- **Estop** (latch): triggered by the `ESTOP` command or a physical estop button
  (GPIO). Motors stay disabled until `RESET`. A latched estop rejects `MV` and
  answers every command with `ERR ESTOP`.

## Errors

`ERR <reason>` — e.g. `ERR ESTOP`, `ERR PARSE`, `ERR RANGE`.

## Pin map

Defined in `firmware/config.h` as `#define`s. These are **placeholders** until the
chassis is wired; adjust once the H-bridge, encoders, and sensors are mounted.
