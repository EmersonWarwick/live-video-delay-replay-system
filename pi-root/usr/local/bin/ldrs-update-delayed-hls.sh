#!/usr/bin/env bash
# Keep delayed HLS playlists aligned with LIVE_DELAY (Wi-Fi + 4K HDMI).
set -euo pipefail

# shellcheck disable=SC1091
source /usr/local/bin/ldrs-delay-env.sh

PYTHON=/usr/local/bin/ldrs-python3.sh
LOG=/var/log/sportassist/hls-delay-updater.log
PLAYLIST_WIFI=/var/lib/sportassist/hls/live.m3u8
DELAYED_SYNC=/var/lib/sportassist/hls/delayed_sync.m3u8
PLAYLIST_4K=/var/lib/sportassist/hls-4k/live.m3u8
DELAYED_HDMI=/var/lib/sportassist/hls-4k/delayed_hdmi.m3u8

mkdir -p /var/log/sportassist
echo "$(date -Iseconds) start wifi offset=${PLAYBACK_OFFSET}s hdmi offset=${PLAYBACK_OFFSET}s" >>"$LOG"

replay_active() {
  systemctl is-active --quiet ldrs-replay-buffer.service
}

while true; do
  if ! replay_active; then
    sleep 2
    continue
  fi
  # shellcheck disable=SC1091
  source /usr/local/bin/ldrs-delay-env.sh

  if [[ -f "$PLAYLIST_WIFI" ]]; then
    if ! "$PYTHON" -m lib.wifi_scrub_playlist \
      "$PLAYLIST_WIFI" "$DELAYED_SYNC" "$PLAYBACK_OFFSET" --hdmi-trim \
      2>>"$LOG"; then
      echo "$(date -Iseconds) warn: failed to build $DELAYED_SYNC" >>"$LOG"
    fi
  fi

  if [[ -f "$PLAYLIST_4K" ]]; then
    if ! "$PYTHON" -m lib.wifi_scrub_playlist \
      "$PLAYLIST_4K" "$DELAYED_HDMI" "$PLAYBACK_OFFSET" --hdmi-trim \
      2>>"$LOG"; then
      echo "$(date -Iseconds) warn: failed to build $DELAYED_HDMI" >>"$LOG"
    fi
  fi

  sleep 0.5
done
