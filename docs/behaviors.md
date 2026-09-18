# Roamer Behaviors — attachable on-the-fly code

Behaviors are self-contained scripts giving the roamer reusable, situational reflexes
(patrol, wall-follow, dock, "turn toward the sound") without touching roamerd's core.
Attached and swapped at runtime, never by editing the main loop.

## Safety boundary (non-negotiable)

A behavior never touches motors or the Pico directly. It **emits goal commands** through
`ctx` (`drive`, `look_at`, `stop`, …), and the arbiter applies the same speed caps,
bumper/cliff aborts, and watchdog it applies to any controller. A broken or hostile
behavior degrades to "roamer stops," never "drives into a wall." Exceptions are caught;
a hung behavior is force-detached.

## Lifecycle API

```python
class Behavior:
    name = "wall_follow"; version = 1
    def on_load(self, ctx): ...        # validate, grab resources
    def on_enter(self, ctx, args): ... # became active
    def tick(self, dt, state): ...     # 10–50 Hz, returns goal commands
    def on_event(self, evt): ...       # bump/cliff/telemetry events
    def on_exit(self, ctx): ...        # releasing cleanly
```

## Attaching on the fly

| Endpoint | Purpose |
|---|---|
| `POST /behaviors` `{name, code}` | validate + load into `scratch/` namespace |
| `POST /behavior/activate` `{name, args}` | arbitrate and switch the active slot |
| `POST /behavior/deactivate` | release the active behavior |
| `GET /behaviors` | list loaded + status |
| `DELETE /behaviors/<name>` | unload |

Two namespaces keep "blessed" vs "scratch" honest:

- `behaviors/` (git-managed) — canonical, repo-reviewed, promoted from scratch once proven.
- `scratch/` (runtime uploads) — survives reboot, clearly not canonical.

## Locked decisions

- In-process (trusted code: Guppy + Sydney). Subprocess isolation is the escalation
  path only if third-party code is ever loaded.
- One active behavior at a time (sub-behaviors can be composed later).
- Release/lease-lapse auto-deactivates the active behavior.
