#!/usr/bin/env bash
# Start HDMI idle logo (no-op if already running).
set -euo pipefail

SYSTEM_ENV=/etc/sportassist/system.env
if [[ -f "$SYSTEM_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$SYSTEM_ENV"
fi
[[ "${HDMI_ENABLED:-1}" == "1" ]] || exit 0
[[ "${HDMI_OUTPUT_MODE:-delayed}" == "live" ]] && exit 0

sudo systemctl start ldrs-hdmi-idle.service
