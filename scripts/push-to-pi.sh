#!/usr/bin/env bash
# Pack pi-root and copy to the Pi. Run on the build PC (Mac/Linux), not on the Pi.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PI_HOST="${PI_HOST:-sportassist@sport-assist.local}"
SERIAL="${1:-}"

"$ROOT/scripts/pack-pi-root.sh" "$ROOT/pi-root-sync.tar.gz"

echo "Copying to ${PI_HOST}..."
scp "$ROOT/pi-root-sync.tar.gz" "$ROOT/requirements-pip.txt" "${PI_HOST}:/home/sportassist/"

if [[ -n "$SERIAL" ]]; then
  APPLIANCE="config/appliance-${SERIAL}.env"
  WEB="config/web-${SERIAL}.env"
  if [[ ! -f "$APPLIANCE" || ! -f "$WEB" ]]; then
    echo "Missing $APPLIANCE or $WEB — create from config/*.example (§7)" >&2
    exit 1
  fi
  scp "$APPLIANCE" "${PI_HOST}:/home/sportassist/appliance.env"
  scp "$WEB" "${PI_HOST}:/home/sportassist/web.env"
  echo "Copied construction env files for serial ${SERIAL}"
fi

echo "Done. On the Pi: ls -la /home/sportassist/pi-root-sync.tar.gz"
