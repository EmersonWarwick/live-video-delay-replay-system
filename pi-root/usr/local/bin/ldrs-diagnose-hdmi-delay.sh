#!/usr/bin/env bash
# Report HDMI delayed HLS pipeline and Wi-Fi delay config.
set -euo pipefail

# shellcheck disable=SC1091
[[ -f /usr/local/bin/ldrs-delay-env.sh ]] && source /usr/local/bin/ldrs-delay-env.sh

echo "=== delay config ==="
if [[ -f /etc/sportassist/system.env ]]; then
  grep -E '^(LIVE_DELAY_SECONDS|PIPELINE_LATENCY_SECONDS|HDMI_PLAYBACK_BIAS_SECONDS|HDMI_OUTPUT_MODE|HDMI_ENABLED)=' /etc/sportassist/system.env || true
fi
echo "HDMI wall-clock delay=${LIVE_DELAY_SECONDS:-?}s  Wi-Fi HLS offset=${PLAYBACK_OFFSET:-?}s"

echo ""
echo "=== 4K HDMI HLS ==="
for path in /var/lib/sportassist/hls-4k/live.m3u8 /var/lib/sportassist/hls-4k/delayed_hdmi.m3u8; do
  if [[ -f "$path" ]]; then
    age=$(( $(date +%s) - $(stat -c %Y "$path") ))
    segs=$(grep -c '^#EXTINF' "$path" 2>/dev/null || echo 0)
    echo "$(basename "$path"): $segs segments, age=${age}s"
  else
    echo "$(basename "$path"): MISSING"
  fi
done
echo "4K segments on disk: $(ls /var/lib/sportassist/hls-4k/*.m4s 2>/dev/null | wc -l)"

echo ""
echo "=== services ==="
for unit in ldrs-replay-buffer ldrs-hls-delay-playlists ldrs-hdmi-delay ldrs-hdmi-live; do
  printf "%s: " "$unit"
  systemctl is-active "${unit}.service" 2>/dev/null || echo inactive
done

echo ""
echo "=== player ==="
if command -v mpv >/dev/null 2>&1; then
  echo "mpv: $(mpv --version | head -1)"
else
  echo "mpv: not installed (using cvlc fallback)"
fi
pgrep -a mpv 2>/dev/null || echo "no mpv process"

echo ""
echo "=== Wi-Fi delayed playlist ==="
path=/var/lib/sportassist/hls/delayed_sync.m3u8
if [[ -f "$path" ]]; then
  age=$(( $(date +%s) - $(stat -c %Y "$path") ))
  segs=$(grep -c '^#EXTINF' "$path" || echo 0)
  echo "delayed_sync: $segs segments, age=${age}s"
else
  echo "delayed_sync: MISSING"
fi

echo ""
echo "=== recent logs ==="
for log in /var/log/sportassist/hdmi-delay.log; do
  echo "-- $(basename "$log") --"
  if [[ -f "$log" ]]; then
    tail -6 "$log"
  else
    echo "(none)"
  fi
done

echo ""
echo "=== /api/status ==="
curl -sS http://127.0.0.1:8080/api/status 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    keys = (
        'liveDelaySeconds','hdmiDelaySeconds','delayedHdmiReady','delayedSyncReady',
        'playbackOffsetSeconds','hdmiOutputMode','replayBufferActive',
    )
    for k in keys:
        print(f'{k}: {d.get(k)}')
except Exception as e:
    print('unavailable:', e)
" || true
