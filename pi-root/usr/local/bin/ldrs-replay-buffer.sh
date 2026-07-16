#!/usr/bin/env bash
# RTSP ingest → dual fMP4 HLS buffers (4K HDMI + 1080p Wi‑Fi) — spec-hls-replay-buffer.md
set -euo pipefail

SYSTEM_ENV=/etc/sportassist/system.env
CAMERA_ENV=/etc/sportassist/camera.env

[[ -f "$SYSTEM_ENV" ]] && source "$SYSTEM_ENV"
[[ -f "$CAMERA_ENV" ]] || { echo "Missing camera.env — configure camera in Settings" >&2; exit 1; }
source "$CAMERA_ENV"

: "${CAMERA_USERNAME:?CAMERA_USERNAME required}"
: "${CAMERA_PASSWORD:?CAMERA_PASSWORD required}"
: "${CAMERA_RTSP_PATH:?CAMERA_RTSP_PATH required — run stream configure in Settings}"
: "${HLS_SEGMENT_DURATION:=1}"
: "${BUFFER_DURATION_SECONDS:=1200}"

HLS_WIFI=/var/lib/sportassist/hls
HLS_HDMI=/var/lib/sportassist/hls-4k
RUN=/run/sportassist
HLS_LIST_SIZE=$((BUFFER_DURATION_SECONDS / HLS_SEGMENT_DURATION))
RETRY_PAUSE="${LDRS_CAMERA_RETRY_SECONDS:-10}"

mkdir -p "$HLS_WIFI" "$HLS_HDMI" "$RUN"

FFMPEG_LIVE_IN=(
  -fflags +nobuffer+discardcorrupt
  -flags low_delay
  -max_delay 500000
  -probesize 500000
  -analyzeduration 500000
  -rtsp_transport tcp
)

run_ffmpeg() {
  local ip="$1"
  local RTSP_MAIN="rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${ip}:${CAMERA_RTSP_PORT:-554}${CAMERA_RTSP_PATH}"

  if [[ -n "${CAMERA_RTSP_PATH_SUB:-}" ]]; then
    local RTSP_SUB="rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${ip}:${CAMERA_RTSP_PORT:-554}${CAMERA_RTSP_PATH_SUB}"
    ffmpeg -hide_banner -loglevel warning -y \
      "${FFMPEG_LIVE_IN[@]}" -i "$RTSP_MAIN" \
      "${FFMPEG_LIVE_IN[@]}" -i "$RTSP_SUB" \
      -an \
      -map 0:v:0 -c:v copy -f hls -hls_segment_type fmp4 \
        -hls_time "$HLS_SEGMENT_DURATION" -hls_list_size "$HLS_LIST_SIZE" \
        -hls_flags delete_segments+append_list \
        "${HLS_HDMI}/live.m3u8" \
      -map 1:v:0 -c:v copy -f hls -hls_segment_type fmp4 \
        -hls_time "$HLS_SEGMENT_DURATION" -hls_list_size "$HLS_LIST_SIZE" \
        -hls_flags delete_segments+append_list \
        "${HLS_WIFI}/live.m3u8"
  else
    ffmpeg -hide_banner -loglevel warning -y \
      "${FFMPEG_LIVE_IN[@]}" -i "$RTSP_MAIN" \
      -an \
      -map 0:v:0 -c:v copy -f hls -hls_segment_type fmp4 \
        -hls_time "$HLS_SEGMENT_DURATION" -hls_list_size "$HLS_LIST_SIZE" \
        -hls_flags delete_segments+append_list \
        "${HLS_HDMI}/live.m3u8" \
      -map 0:v:0 -c:v copy -f hls -hls_segment_type fmp4 \
        -hls_time "$HLS_SEGMENT_DURATION" -hls_list_size "$HLS_LIST_SIZE" \
        -hls_flags delete_segments+append_list \
        "${HLS_WIFI}/live.m3u8"
  fi
}

while true; do
  echo "Waiting for camera network and RTSP (up to ${LDRS_CAMERA_WAIT_SECONDS:-300}s)…" >&2
  if ! /usr/local/bin/ldrs-wait-for-camera.sh; then
    echo "Camera not reachable — retrying in ${RETRY_PAUSE}s" >&2
    sleep "$RETRY_PAUSE"
    continue
  fi

  RUN_IP=/run/sportassist/camera.ip
  CAMERA_IP=""
  [[ -f "$RUN_IP" ]] && CAMERA_IP="$(tr -d '[:space:]' < "$RUN_IP")"
  if [[ -z "$CAMERA_IP" ]]; then
    echo "No camera IP after wait — retrying in ${RETRY_PAUSE}s" >&2
    sleep "$RETRY_PAUSE"
    continue
  fi

  echo "Ingest from camera ${CAMERA_IP}" >&2
  run_ffmpeg "$CAMERA_IP" || true
  echo "Ingest stopped — waiting for camera again" >&2
  sleep "$RETRY_PAUSE"
done
