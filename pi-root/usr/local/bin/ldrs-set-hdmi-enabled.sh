#!/usr/bin/env bash
# Set HDMI_ENABLED — stop both HDMI services or re-activate current mode
set -euo pipefail

CFG=/etc/sportassist/system.env
ENABLED="${1:-}"

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 2
fi

if [[ "$ENABLED" != "0" && "$ENABLED" != "1" ]]; then
  echo "HDMI enabled must be 0 or 1" >&2
  exit 1
fi

cp -a "$CFG" "${CFG}.bak"
if grep -q '^HDMI_ENABLED=' "$CFG"; then
  sed -i "s/^HDMI_ENABLED=.*/HDMI_ENABLED=${ENABLED}/" "$CFG"
else
  echo "HDMI_ENABLED=${ENABLED}" >> "$CFG"
fi

# shellcheck disable=SC1090
source "$CFG"
MODE="${HDMI_OUTPUT_MODE:-delayed}"
/usr/local/bin/ldrs-hdmi-activate.sh "$MODE"
echo "HDMI_ENABLED=${ENABLED}"
