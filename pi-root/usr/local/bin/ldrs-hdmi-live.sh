#!/usr/bin/env bash
# Live to HDMI — direct RTSP (cvlc preferred, mpv fallback).
set -euo pipefail

CAMERA_ENV=/etc/sportassist/camera.env
SYSTEM_ENV=/etc/sportassist/system.env
RUN_IP=/run/sportassist/camera.ip
LOG=/var/log/sportassist/hdmi-live.log

log() {
  echo "$(date -Iseconds) $*" | tee -a "$LOG" >&2
}

[[ -f "$SYSTEM_ENV" ]] && source "$SYSTEM_ENV"
: "${HDMI_ENABLED:=1}"
[[ "$HDMI_ENABLED" == "1" ]] || exit 0
[[ -f "$CAMERA_ENV" ]] || { log "Missing camera.env"; exit 1; }
# shellcheck disable=SC1090
source "$CAMERA_ENV"

: "${CAMERA_IP:?CAMERA_IP required}"
: "${CAMERA_USERNAME:?CAMERA_USERNAME required}"
: "${CAMERA_PASSWORD:?CAMERA_PASSWORD required}"
: "${CAMERA_RTSP_PATH:?CAMERA_RTSP_PATH required}"

read_camera_ip() {
  if [[ -f "$RUN_IP" ]]; then
    tr -d '[:space:]' < "$RUN_IP"
  else
    echo "$CAMERA_IP"
  fi
}

build_rtsp_url() {
  /usr/local/bin/ldrs-rtsp-url.sh \
    "$(read_camera_ip)" "${CAMERA_RTSP_PORT:-554}" "$CAMERA_RTSP_PATH" \
    "$CAMERA_USERNAME" "$CAMERA_PASSWORD"
}

play_live() {
  local rtsp_url="$1"
  /usr/local/bin/ldrs-hdmi-idle-stop.sh
  if command -v cvlc >/dev/null 2>&1; then
    log "cvlc live RTSP → HDMI"
    cvlc "$rtsp_url" \
      --rtsp-tcp \
      --rtsp-frame-buffer-size=10000000 \
      --live-caching=0 \
      --network-caching=0 \
      --file-caching=0 \
      --clock-jitter=0 \
      --clock-synchro=0 \
      --no-audio \
      --fullscreen --no-video-title-show --quiet
    return
  fi
  if command -v mpv >/dev/null 2>&1; then
    log "mpv live RTSP → HDMI (fallback)"
    mpv --no-config --hwdec=v4l2m2m \
      --rtsp-transport=tcp \
      --cache=yes --demuxer-max-bytes=100M \
      --no-audio --fullscreen --force-window=immediate \
      --msg-level=all=warn \
      "$rtsp_url"
    return
  fi
  log "No HDMI player (cvlc/mpv) installed"
  return 1
}

log "Live HDMI pipeline: RTSP direct ($(read_camera_ip)${CAMERA_RTSP_PATH})"
/usr/local/bin/ldrs-hdmi-idle-stop.sh

while true; do
  RTSP_URL="$(build_rtsp_url)"
  play_live "$RTSP_URL" >>"$LOG" 2>&1 || true
  log "live player exited — retry in 2s"
  /usr/local/bin/ldrs-hdmi-idle-start.sh
  sleep 2
done
