#!/usr/bin/env bash
# Update IDLE_SPLASH_ROTATION in system.env — rebuild idle splash and refresh HDMI logo.
set -euo pipefail

CFG=/etc/sportassist/system.env
ROT="${1:-}"

if [[ "$ROT" != "-90" && "$ROT" != "0" && "$ROT" != "90" ]]; then
  echo "Rotation must be -90, 0, or 90" >&2
  exit 1
fi

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 2
fi

cp -a "$CFG" "${CFG}.bak"
if grep -q '^IDLE_SPLASH_ROTATION=' "$CFG"; then
  sed -i "s/^IDLE_SPLASH_ROTATION=.*/IDLE_SPLASH_ROTATION=${ROT}/" "$CFG"
else
  echo "IDLE_SPLASH_ROTATION=${ROT}" >> "$CFG"
fi

/usr/local/bin/ldrs-build-idle-splash.sh --force

if systemctl is-active --quiet ldrs-hdmi-idle.service 2>/dev/null; then
  systemctl restart ldrs-hdmi-idle.service
fi

echo "IDLE_SPLASH_ROTATION=${ROT}"
