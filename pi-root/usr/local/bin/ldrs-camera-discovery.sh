#!/usr/bin/env bash
# Resolve camera IP — direct DHCP, hostname lookup, or network search by device ID
set -euo pipefail

CFG=/etc/sportassist/camera.env
NET=/etc/sportassist/network.env
RUN=/run/sportassist
mkdir -p "$RUN"

if [[ -f "$NET" ]]; then
  # shellcheck disable=SC1090
  source "$NET"
  if [[ "${ETH_CAMERA_DHCP:-1}" == "1" ]]; then
    /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/apply_direct_discovery.py || true
  fi
fi

if [[ ! -f "$CFG" ]]; then
  echo "camera.env not configured yet"
  exit 0
fi
# shellcheck disable=SC1090
source "$CFG"

# Assigned camera: verify saved IP or search network by device identifier
  if [[ "${CAMERA_ASSIGNED:-0}" == "1" && -n "${CAMERA_RTSP_PATH:-}" ]]; then
  /usr/local/bin/ldrs-resolve-camera.sh || true
  if [[ -f "${RUN}/camera.ip" ]]; then
    /usr/local/bin/ldrs-verify-camera-credentials.sh || true
    exit 0
  fi
fi

if [[ -n "${CAMERA_IP:-}" ]]; then
  echo "$CAMERA_IP" > "${RUN}/camera.ip"
  echo "Camera IP ${CAMERA_IP}"
  exit 0
fi

if [[ -n "${CAMERA_HOSTNAME:-}" ]]; then
  ip="$(getent hosts "$CAMERA_HOSTNAME" 2>/dev/null | awk '{print $1; exit}')" || ip=""
  if [[ -n "$ip" ]]; then
    echo "$ip" > "${RUN}/camera.ip"
    echo "Resolved ${CAMERA_HOSTNAME} -> ${ip}"
    exit 0
  fi
fi

echo "Camera not configured or not reachable"
exit 0
