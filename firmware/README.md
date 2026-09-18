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
printf 'PING\n' > /dev/ttyACM0    # → PONG 0.1.0 <ms>
```

`MV`, `STOP`, `ESTOP`, `RESET` are all safe with no H-bridge attached; encoders read
0 and the PID drives PWM to 0. `ESTOP` latches (subsequent `MV` → `ERR ESTOP`) until
`RESET`. Telemetry streams at 20 Hz.
