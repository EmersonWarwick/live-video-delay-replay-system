#!/usr/bin/env bash
# Install per-unit web.env from construction copy — build-instructions §8.
set -euo pipefail

SRC="${1:-/home/sportassist/web.env}"
DEST=/etc/sportassist/web.env

if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC — run push-to-pi.sh on the Mac or copy web-{serial}.env to the Pi" >&2
  exit 2
fi

if ! grep -qE '^SETTINGS_PASSWORD=.+' "$SRC"; then
  echo "SETTINGS_PASSWORD is empty in $SRC" >&2
  exit 1
fi

install -m 640 -o root -g sportassist "$SRC" "$DEST"
echo "Installed $DEST"
