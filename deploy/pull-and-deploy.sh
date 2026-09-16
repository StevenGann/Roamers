#!/usr/bin/env bash
# Pull-based deploy for Roamer-1. Invoked by roamer-pull.timer every 5 min.
# Fetches origin/main, and on change: git pull --ff-only, restart roamerd if its
# code changed, and log a manual-reflash notice if pico-firmware changed.
set -euo pipefail

REPO_DIR="/opt/roamers"
cd "$REPO_DIR"

git fetch --quiet origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

# Nothing new — exit quietly (this is the common case).
if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0
fi

CHANGED_FILES=$(git diff --name-only "$LOCAL" "$REMOTE")
git pull --quiet --ff-only origin main

# Restart roamerd only when its own code changed. Guarded so this is a no-op
# until roamerd is installed; docs/deploy-only changes don't bounce the daemon.
if printf '%s\n' "$CHANGED_FILES" | grep -q '^roamerd/'; then
  if systemctl is-active --quiet roamerd 2>/dev/null; then
    systemctl restart roamerd
  fi
fi

# pico-firmware changes are NEVER auto-flashed over USB — surface a notice only.
if printf '%s\n' "$CHANGED_FILES" | grep -q '^pico-firmware/'; then
  logger -t roamer-pull "pico-firmware changed — manual re-flash required (git $REMOTE)"
fi
