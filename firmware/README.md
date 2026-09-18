# roamer_pico — the fast loop (RP2350-Zero)

Firmware for the RP2350-Zero on Roamer-01. Owns motor velocity PID, wheel-encoder
counting, and the bumper/cliff/wheel-drop safety stop, independent of the Pi.

Protocol: see [`../docs/pico-protocol.md`](../docs/pico-protocol.md).

## Build

On the Pi (or any host with the Pico SDK toolchain):

```bash
export PICO_SDK_PATH=$HOME/pico-sdk
mkdir -p build && cd build
cmake -DPICO_PLATFORM=rp2350 -DPICO_SDK_PATH=$PICO_SDK_PATH ..
make -j4
```

Produces `build/roamer_pico.uf2`.

## Flash

```bash
# if the board is running (USB CDC), reboot it into BOOTSEL:
picotool reboot -u -f
sleep 2
picotool load build/roamer_pico.uf2
picotool reboot
```

Or hold BOOT while plugging in, then copy `roamer_pico.uf2` onto the `RP2350`
mass-storage device.

## Test on the bench (no motors wired)

```bash
# on the Pi, talk over ttyACM0
printf 'PING\n' > /dev/ttyACM0
# expect: PONG 0.1.0 <ms>
```

`MV`, `STOP`, `ESTOP`, `RESET` are all safe to exercise with no H-bridge attached;
encoders read 0 and the PID just drives PWM to 0 with no motor present.
