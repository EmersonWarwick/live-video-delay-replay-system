#!/usr/bin/env bash
# Stop every video pipeline — replay ingest, delayed HDMI (HLS), live HDMI (RTSP).
set -euo pipefail

force_stop() {
  local unit="$1"
  systemctl stop "${unit}.service" 2>/dev/null || true
  for _ in $(seq 1 15); do
    systemctl is-active -q "${unit}.service" || return 0
    sleep 1
  done
  systemctl kill -s SIGKILL "${unit}.service" 2>/dev/null || true
  systemctl reset-failed "${unit}.service" 2>/dev/null || true
}

force_stop ldrs-hdmi-delay
force_stop ldrs-hdmi-live
force_stop ldrs-hls-delay-playlists
force_stop ldrs-replay-buffer

pkill -f 'file:///var/lib/sportassist/hls' 2>/dev/null || true
pkill -f 'http://127.0.0.1:8080/hls-4k/delayed_hdmi' 2>/dev/null || true
pkill -f 'delayed_hdmi.m3u8' 2>/dev/null || true
pkill -f '/var/lib/sportassist/hls-4k/live.m3u8' 2>/dev/null || true
pkill -f 'ffmpeg.*var/lib/sportassist/hls' 2>/dev/null || true

echo "Video pipelines stopped"
