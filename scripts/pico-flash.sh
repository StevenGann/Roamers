#!/usr/bin/env bash
# Build + flash the RP2350 firmware. Idempotent: skips work if the Pico is
# already running the version in main.c (tracked by the marker file). Run at
# boot by pico-flash.service, before roamerd starts.
set -euo pipefail

REPO=/opt/roamers
BUILD="$REPO/firmware/build"
UF2="$BUILD/roamer_pico.uf2"
MARK="$REPO/.pico-flash-marker"

cd "$REPO"
git pull --ff-only --quiet 2>/dev/null || true   # best-effort source update

SRCVER=$(grep -oP '#define VERSION "\K[^"]+' "$REPO/firmware/main.c")
if [ "$SRCVER" = "$(cat "$MARK" 2>/dev/null || true)" ]; then
    echo "pico-flash: already on $SRCVER"
    exit 0
fi

# wait for the Pico to enumerate (up to ~10s)
for _ in $(seq 1 20); do
    [ -e /dev/ttyACM0 ] && break
    sleep 0.5
done

export PICO_SDK_PATH="${PICO_SDK_PATH:-/home/guppy/pico-sdk}"
cd "$BUILD"
make -j"$(nproc)"

if picotool load -f -x "$UF2" 2>/dev/null; then
    echo "$SRCVER" > "$MARK"
    echo "pico-flash: flashed $SRCVER"
else
    echo "pico-flash: Pico not found; will retry next boot"
fi
