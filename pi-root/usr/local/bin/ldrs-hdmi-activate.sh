#!/usr/bin/env bash
# Activate HDMI mode — live (VLC RTSP only) or delayed (clear HLS + fresh replay pipeline).
set -euo pipefail

MODE="${1:-delayed}"
SYSTEM_ENV=/etc/sportassist/system.env

if [[ ! -f "$SYSTEM_ENV" ]]; then
  /usr/local/bin/ldrs-stop-video-pipelines.sh
  systemctl enable ldrs-replay-buffer.service 2>/dev/null || true
  systemctl start --no-block ldrs-replay-buffer.service 2>/dev/null || true
  exit 0
fi
# shellcheck disable=SC1090
source "$SYSTEM_ENV"

if [[ "${HDMI_ENABLED:-1}" != "1" ]]; then
  /usr/local/bin/ldrs-stop-video-pipelines.sh
  systemctl disable ldrs-hdmi-delay.service 2>/dev/null || true
  systemctl disable ldrs-hdmi-live.service 2>/dev/null || true
  systemctl stop ldrs-hdmi-idle.service 2>/dev/null || true
  systemctl disable ldrs-hdmi-idle.service 2>/dev/null || true
  /usr/local/bin/ldrs-clear-hls-buffers.sh
  systemctl enable ldrs-replay-buffer.service 2>/dev/null || true
  systemctl start --no-block ldrs-replay-buffer.service 2>/dev/null || true
  echo "HDMI disabled — replay buffer active for tablets"
  exit 0
fi

if [[ "$MODE" != "delayed" && "$MODE" != "live" ]]; then
  echo "Invalid HDMI mode: $MODE" >&2
  exit 1
fi

/usr/local/bin/ldrs-apply-hdmi-resolution.sh 2>/dev/null || true
/usr/local/bin/ldrs-stop-video-pipelines.sh

if [[ "$MODE" == "live" ]]; then
  systemctl stop ldrs-hdmi-idle.service 2>/dev/null || true
  systemctl disable ldrs-replay-buffer.service 2>/dev/null || true
  systemctl disable ldrs-hdmi-delay.service 2>/dev/null || true
  systemctl enable ldrs-hdmi-live.service
  systemctl start --no-block ldrs-hdmi-live.service
  echo "Live HDMI: VLC RTSP only — replay and delayed pipelines stopped"
else
  systemctl enable ldrs-hdmi-idle.service 2>/dev/null || true
  systemctl start --no-block ldrs-hdmi-idle.service 2>/dev/null || true
  /usr/local/bin/ldrs-clear-hls-buffers.sh
  systemctl disable ldrs-hdmi-live.service 2>/dev/null || true
  systemctl enable ldrs-replay-buffer.service
  systemctl start --no-block ldrs-replay-buffer.service
  systemctl enable ldrs-hdmi-delay.service
  systemctl start --no-block ldrs-hdmi-delay.service
  echo "Delayed HDMI: HLS buffers cleared — fresh replay pipeline starting"
fi
