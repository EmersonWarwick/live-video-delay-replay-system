#!/usr/bin/env bash
# Production unit with assigned camera — enable camera network, discovery, replay, HDMI.
set -euo pipefail

CFG=/etc/sportassist/camera.env
[[ -f "$CFG" ]] || exit 0
# shellcheck disable=SC1090
source "$CFG"
[[ "${CAMERA_ASSIGNED:-0}" == "1" ]] || exit 0
[[ -n "${CAMERA_RTSP_PATH:-}" ]] || exit 0

for unit in \
  ldrs-network.service \
  ldrs-camera-discovery.service \
  ldrs-camera-watch.timer \
  ldrs-replay-buffer.service \
  ldrs-hdmi-apply.service; do
  systemctl enable "$unit" 2>/dev/null || true
done

systemctl start ldrs-network.service 2>/dev/null || true
systemctl start ldrs-camera-watch.timer 2>/dev/null || true

# Do not systemctl start discovery/replay/hdmi here — they have After=ldrs-commissioned-boot
# and blocking systemctl start from inside this oneshot deadlocks boot.

timeout 20 /usr/local/bin/ldrs-verify-camera-credentials.sh 2>/dev/null || {
  echo "Camera credential check skipped or failed (camera may still be booting)" >&2
}
