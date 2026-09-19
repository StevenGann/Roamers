# roamer_pico — the fast loop (RP2350-Zero)

Firmware for the RP2350-Zero on Roamer-01. Owns motor velocity PID, wheel-encoder
counting, and the bumper/cliff/wheel-drop safety stop, independent of the Pi.

Protocol: see [`../docs/pico-protocol.md`](../docs/pico-protocol.md).

## Build (on the Pi)

Prereqs — host build tools, because the SDK builds picotool for its disassembly step:

```bash
sudo apt-get install -y gcc-arm-none-eabi cmake ninja-build gcc g++ libusb-1.0-0-dev pkg-config git
git clone --depth 1 --recurse-submodules https://github.com/raspberrypi/pico-sdk.git ~/pico-sdk
```

Build:

```bash
export PICO_SDK_PATH=$HOME/pico-sdk
mkdir -p build && cd build
cmake -DPICO_BOARD=pico2 -DPICOTOOL_FORCE_FETCH_FROM_GIT=ON -DPICO_SDK_PATH=$PICO_SDK_PATH ..
make -j4
```

Produces `build/roamer_pico.uf2`.

Two gotchas baked into the flags above:

- `-DPICO_BOARD=pico2` — an RP2350 board. The default `pico` board is RP2040 and
  fails the `boot_stage2` config with "Configuring incomplete".
- `-DPICOTOOL_FORCE_FETCH_FROM_GIT=ON` — the apt `picotool` (2.1.1) is too old for
  the SDK's disassembly step ("Requires version 2.3.0"); this fetches+builds 2.3.0.

## Flash — use the SYSTEM picotool, not the SDK-fetched one

The SDK-fetched picotool is compiled WITHOUT USB support (it exists only for
disassembly). The apt `/usr/bin/picotool` has USB support and handles RP2350:

```bash
picotool reboot -u -f      # reboot the running Pico into BOOTSEL via USB
sleep 2
picotool load build/roamer_pico.uf2
picotool reboot            # run the new firmware (load may leave it in BOOTSEL)
```

Or hold BOOT while powering, then copy `roamer_pico.uf2` onto the `RP2350` drive.

## Test (no motors wired)

```bash
printf 'PING\n' > /dev/ttyACM0    # → PONG <version> <ms>
```

`MV`, `STOP`, `ESTOP`, `RESET` are all safe with no H-bridge attached. `ESTOP`
latches (subsequent `MV` → `ERR ESTOP`) until `RESET`. Telemetry streams at 20 Hz.

> The Pi auto-flashes the Pico on boot (`pico-flash.service` → `scripts/pico-flash.sh`),
> so firmware updates are just "push → reboot".

## No-encoder behaviour (important)

The velocity PID assumes wheel encoders. With **no encoders wired**, `encoder_*()`
returns 0 forever, so:

- any non-zero `MV` saturates the output to full duty (the P term sees `target−0`),
  so "3 cm/s" actually means "full speed";
- a wound-up integral once kept the motors spinning after `STOP` (target→0, but the
  integral never decayed since error stays 0).

Both are handled in `motor_tick()`: it zeroes the integral when the target is 0, and
uses anti-windup (only integrates while the output isn't saturated). When the chassis
gets encoders, tune the PID in `config.h` and this section becomes moot.
