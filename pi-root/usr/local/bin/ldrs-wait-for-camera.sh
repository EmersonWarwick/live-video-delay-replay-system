#!/usr/bin/env bash
# Block until camera RTSP is reachable (camera may boot slower than the Pi).
set -euo pipefail

MAX_WAIT="${LDRS_CAMERA_WAIT_SECONDS:-300}"
exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/wait_for_camera.py "$MAX_WAIT"
