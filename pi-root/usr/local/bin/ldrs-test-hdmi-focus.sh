#!/usr/bin/env bash
# Diagnose live focus HDMI — run on Pi after assign/configure.
set -euo pipefail

echo "=== HDMI mode (system.env) ==="
grep -E '^HDMI_' /etc/sportassist/system.env 2>/dev/null || echo "(no system.env)"

echo
echo "=== Services ==="
systemctl is-active ldrs-hdmi-live.service ldrs-hdmi-delay.service ldrs-replay-buffer.service 2>/dev/null \
  | paste - - - | awk '{print "live="$1, "delayed="$2, "replay="$3}'

echo
echo "=== Camera IP ==="
cat /run/sportassist/camera.ip 2>/dev/null || grep ^CAMERA_IP= /etc/sportassist/camera.env

echo
echo "=== RTSP probe ==="
set -a
# shellcheck disable=SC1091
source /etc/sportassist/camera.env
set +a
IP="$(tr -d '[:space:]' < /run/sportassist/camera.ip 2>/dev/null || echo "$CAMERA_IP")"
URL="$(/usr/local/bin/ldrs-rtsp-url.sh "$IP" "${CAMERA_RTSP_PORT:-554}" "$CAMERA_RTSP_PATH" "$CAMERA_USERNAME" "$CAMERA_PASSWORD")"
ffprobe -hide_banner -rtsp_transport tcp -probesize 500000 -analyzeduration 500000 \
  -i "$URL" -show_streams 2>&1 | head -25

echo
echo "=== hdmi-live log (last 20 lines) ==="
tail -20 /var/log/sportassist/hdmi-live.log 2>/dev/null || echo "(no log yet)"

echo
echo "=== Apply focus mode now ==="
echo "sudo /usr/local/bin/ldrs-set-hdmi-mode.sh live"
