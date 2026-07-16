#!/usr/bin/env bash
# Set HDMI_OUTPUT_MODE — toggles ldrs-hdmi-delay vs ldrs-hdmi-live services
set -euo pipefail

CFG=/etc/sportassist/system.env
MODE="${1:-}"

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 2
fi

if [[ "$MODE" != "delayed" && "$MODE" != "live" ]]; then
  echo "HDMI mode must be delayed or live" >&2
  exit 1
fi

cp -a "$CFG" "${CFG}.bak"
if grep -q '^HDMI_OUTPUT_MODE=' "$CFG"; then
  sed -i "s/^HDMI_OUTPUT_MODE=.*/HDMI_OUTPUT_MODE=${MODE}/" "$CFG"
else
  echo "HDMI_OUTPUT_MODE=${MODE}" >> "$CFG"
fi

if ! /usr/local/bin/ldrs-hdmi-activate.sh "$MODE"; then
  cp -a "${CFG}.bak" "$CFG"
  echo "HDMI mode activate failed — reverted to previous mode" >&2
  exit 1
fi

echo "HDMI_OUTPUT_MODE=${MODE}"
