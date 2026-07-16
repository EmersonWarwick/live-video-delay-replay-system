#!/usr/bin/env bash
# Set HDMI_RESOLUTION_MODE — auto (EDID negotiate) or force_4k (3840×2160@60).
set -euo pipefail

CFG=/etc/sportassist/system.env
MODE="${1:-}"

if [[ "$MODE" != "auto" && "$MODE" != "force_4k" ]]; then
  echo "usage: ldrs-set-hdmi-resolution.sh auto|force_4k" >&2
  exit 1
fi

[[ -f "$CFG" ]] || { echo "Missing $CFG" >&2; exit 2; }

cp -a "$CFG" "${CFG}.bak"
if grep -q '^HDMI_RESOLUTION_MODE=' "$CFG"; then
  sed -i "s/^HDMI_RESOLUTION_MODE=.*/HDMI_RESOLUTION_MODE=${MODE}/" "$CFG"
else
  echo "HDMI_RESOLUTION_MODE=${MODE}" >> "$CFG"
fi

/usr/local/bin/ldrs-apply-hdmi-resolution.sh

# Refresh fullscreen players so they pick up the new mode.
for svc in ldrs-hdmi-delay.service ldrs-hdmi-live.service ldrs-hdmi-idle.service; do
  if systemctl is-active --quiet "$svc" 2>/dev/null; then
    systemctl restart "$svc" || true
  fi
done

echo "HDMI_RESOLUTION_MODE=${MODE}"
