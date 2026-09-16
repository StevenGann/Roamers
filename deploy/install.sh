#!/usr/bin/env bash
# One-time install for Roamer-1 pull-based deploy.
# Clones the repo to /opt/roamers and installs the pull timer.
# Run on the Pi 5 after first boot:
#   curl -fsSL https://github.com/StevenGann/Roamers/raw/main/deploy/install.sh | sudo bash
set -euo pipefail

REPO="https://github.com/StevenGann/Roamers.git"
TARGET="/opt/roamers"

if [ ! -d "$TARGET/.git" ]; then
  git clone "$REPO" "$TARGET"
fi

install -m 0644 "$TARGET/deploy/roamer-pull.service" /etc/systemd/system/roamer-pull.service
install -m 0644 "$TARGET/deploy/roamer-pull.timer"  /etc/systemd/system/roamer-pull.timer

systemctl daemon-reload
systemctl enable --now roamer-pull.timer

echo "roamer-pull installed. Repo at $TARGET, timer enabled."
