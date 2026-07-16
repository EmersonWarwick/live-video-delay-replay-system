#!/usr/bin/env bash
# 4K HDMI delayed playback — local HLS when dual-stream ingest (camera RTSP limit), else RTSP+cvlc.
set -euo pipefail

# shellcheck disable=SC1091
source /usr/local/bin/ldrs-delay-env.sh
: "${HDMI_ENABLED:=1}"

[[ "$HDMI_ENABLED" == "1" ]] || exit 0

CAMERA_ENV=/etc/sportassist/camera.env
RUN_IP=/run/sportassist/camera.ip
DELAYED_PLAYLIST=/var/lib/sportassist/hls-4k/delayed_hdmi.m3u8
HLS_DIR=/var/lib/sportassist/hls-4k
LOG=/var/log/sportassist/hdmi-delay.log
MAX_PLAYLIST_AGE_S=5

[[ -f "$CAMERA_ENV" ]] || { echo "Missing camera.env" | tee -a "$LOG" >&2; exit 1; }
# shellcheck disable=SC1090
source "$CAMERA_ENV"

hdmi_ready() {
  systemctl is-active --quiet ldrs-replay-buffer.service
}

segment_count() {
  find "$HLS_DIR" -maxdepth 1 -name '*.m4s' 2>/dev/null | wc -l | tr -d ' '
}

playlist_fresh() {
  [[ -f "$DELAYED_PLAYLIST" ]] || return 1
  [[ "$(segment_count)" -ge "$MIN_BUFFER_SEGMENTS" ]] || return 1
  local now age
  now=$(date +%s)
  age=$(( now - $(stat -c %Y "$DELAYED_PLAYLIST") ))
  (( age <= MAX_PLAYLIST_AGE_S ))
}

read_camera_ip() {
  if [[ -f "$RUN_IP" ]]; then
    tr -d '[:space:]' < "$RUN_IP"
  else
    echo "${CAMERA_IP:-}"
  fi
}

build_rtsp_url() {
  /usr/local/bin/ldrs-rtsp-url.sh \
    "$(read_camera_ip)" "${CAMERA_RTSP_PORT:-554}" "$CAMERA_RTSP_PATH" \
    "$CAMERA_USERNAME" "$CAMERA_PASSWORD"
}

use_local_hls() {
  [[ -n "${CAMERA_RTSP_PATH_SUB:-}" ]]
}

/usr/local/bin/ldrs-hdmi-idle-start.sh

if use_local_hls; then
  echo "Waiting for delayed_hdmi.m3u8 (dual-stream ingest — no extra camera RTSP)…" | tee -a "$LOG" >&2
  for _ in $(seq 1 180); do
    if playlist_fresh; then
      break
    fi
    hdmi_ready || sleep 1
    sleep 1
  done
  playlist_fresh || {
    echo "delayed_hdmi.m3u8 not ready — is ldrs-hls-delay-playlists running?" | tee -a "$LOG" >&2
    /usr/local/bin/ldrs-hdmi-idle-start.sh
    exit 1
  }
else
  : "${CAMERA_IP:?CAMERA_IP required}"
  : "${CAMERA_USERNAME:?CAMERA_USERNAME required}"
  : "${CAMERA_PASSWORD:?CAMERA_PASSWORD required}"
  : "${CAMERA_RTSP_PATH:?CAMERA_RTSP_PATH required}"
  echo "Waiting for ingest before delayed RTSP…" | tee -a "$LOG" >&2
  for _ in $(seq 1 120); do
    if hdmi_ready; then
      break
    fi
    sleep 1
  done
  hdmi_ready || {
    echo "Replay buffer not running — cannot start delayed HDMI" | tee -a "$LOG" >&2
    /usr/local/bin/ldrs-hdmi-idle-start.sh
    exit 1
  }
fi

play_hdmi_hls() {
  /usr/local/bin/ldrs-hdmi-idle-stop.sh
  echo "$(date -Iseconds) cvlc delayed HLS total=${LIVE_DELAY_SECONDS}s trim=${PLAYBACK_OFFSET}s" | tee -a "$LOG" >&2
  cvlc "file://${DELAYED_PLAYLIST}" \
    --live-caching=500 \
    --network-caching=300 \
    --file-caching=100 \
    --clock-jitter=0 \
    --clock-synchro=0 \
    --no-audio \
    --fullscreen --no-video-title-show --quiet
}

play_hdmi_rtsp() {
  local rtsp_url="$1"
  local delay="$LIVE_DELAY_SECONDS"
  local cache_ms=$((delay * 1000))
  /usr/local/bin/ldrs-hdmi-idle-stop.sh

  if command -v cvlc >/dev/null 2>&1; then
    echo "$(date -Iseconds) cvlc delayed RTSP wall=${delay}s live-caching=${cache_ms}ms" | tee -a "$LOG" >&2
    cvlc "$rtsp_url" \
      --rtsp-tcp \
      --rtsp-frame-buffer-size=10000000 \
      --live-caching="$cache_ms" \
      --network-caching="$cache_ms" \
      --file-caching=0 \
      --clock-jitter=0 \
      --clock-synchro=0 \
      --no-audio \
      --fullscreen --no-video-title-show --quiet
    return
  fi

  if command -v mpv >/dev/null 2>&1; then
    echo "$(date -Iseconds) mpv delayed RTSP wall=${delay}s" | tee -a "$LOG" >&2
    mpv --no-config --hwdec=v4l2m2m \
      --rtsp-transport=tcp \
      --cache=yes --demuxer-max-bytes=200M --demuxer-max-back-bytes=200M \
      --no-audio --fullscreen --force-window=immediate \
      --msg-level=all=warn \
      "$rtsp_url"
    return
  fi

  echo "No HDMI player (cvlc/mpv) installed" | tee -a "$LOG" >&2
  return 1
}

while true; do
  # shellcheck disable=SC1091
  source /usr/local/bin/ldrs-delay-env.sh

  if use_local_hls; then
    if ! playlist_fresh; then
      echo "delayed_hdmi.m3u8 missing or stale — waiting…" | tee -a "$LOG" >&2
      /usr/local/bin/ldrs-hdmi-idle-start.sh
      sleep 2
      continue
    fi
    play_hdmi_hls 2>>"$LOG" || true
  else
    RTSP_URL="$(build_rtsp_url)"
    echo "$(date -Iseconds) HDMI delay: wall=${LIVE_DELAY_SECONDS}s RTSP $(read_camera_ip)${CAMERA_RTSP_PATH}" | tee -a "$LOG" >&2
    play_hdmi_rtsp "$RTSP_URL" 2>>"$LOG" || true
  fi

  echo "player exited — retrying in 2s" | tee -a "$LOG" >&2
  /usr/local/bin/ldrs-hdmi-idle-start.sh
  sleep 2
done
