#!/usr/bin/env bash
# Boot: apply HDMI_OUTPUT_MODE — start delayed or live service, not both
set -euo pipefail
SYSTEM_ENV=/etc/sportassist/system.env
MODE=delayed
if [[ -f "$SYSTEM_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$SYSTEM_ENV"
  MODE="${HDMI_OUTPUT_MODE:-delayed}"
fi
exec /usr/local/bin/ldrs-hdmi-activate.sh "$MODE"
