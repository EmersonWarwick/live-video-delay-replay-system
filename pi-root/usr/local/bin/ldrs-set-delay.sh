#!/usr/bin/env bash
# Update LIVE_DELAY_SECONDS in system.env — restart HDMI + playlist updater.
set -euo pipefail

CFG=/etc/sportassist/system.env
DELAY_SECONDS="${1:-}"

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$CFG"
: "${PIPELINE_LATENCY_SECONDS:=3}"
MIN="${PIPELINE_LATENCY_SECONDS}"
MAX=60

if ! [[ "$DELAY_SECONDS" =~ ^[0-9]+$ ]] || (( DELAY_SECONDS < MIN || DELAY_SECONDS > MAX )); then
  echo "Delay must be integer ${MIN}-${MAX} (minimum is ingest pipeline latency)" >&2
  exit 1
fi

cp -a "$CFG" "${CFG}.bak"
if grep -q '^LIVE_DELAY_SECONDS=' "$CFG"; then
  sed -i "s/^LIVE_DELAY_SECONDS=.*/LIVE_DELAY_SECONDS=${DELAY_SECONDS}/" "$CFG"
else
  echo "LIVE_DELAY_SECONDS=${DELAY_SECONDS}" >> "$CFG"
fi

systemctl restart ldrs-hls-delay-playlists.service 2>/dev/null || true

# shellcheck disable=SC1090
source "$CFG"
if [[ "${HDMI_ENABLED:-1}" == "1" && "${HDMI_OUTPUT_MODE:-delayed}" == "delayed" ]]; then
  systemctl restart ldrs-hdmi-delay.service 2>/dev/null || true
fi

echo "LIVE_DELAY_SECONDS=${DELAY_SECONDS}"
