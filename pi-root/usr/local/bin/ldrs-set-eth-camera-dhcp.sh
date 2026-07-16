#!/usr/bin/env bash
# Toggle ETH_CAMERA_DHCP — eth0 only; wlan0 SSH/AP is never changed here.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

MODE="${1:-}"
CFG=/etc/sportassist/network.env

if [[ "$MODE" != "enable" && "$MODE" != "disable" ]]; then
  echo "usage: ldrs-set-eth-camera-dhcp.sh enable|disable" >&2
  exit 2
fi

[[ -f "$CFG" ]] || { echo "Missing $CFG" >&2; exit 2; }

cp -a "$CFG" "${CFG}.bak"
if [[ "$MODE" == "enable" ]]; then
  VAL=1
else
  VAL=0
fi

if grep -q '^ETH_CAMERA_DHCP=' "$CFG"; then
  sed -i "s/^ETH_CAMERA_DHCP=.*/ETH_CAMERA_DHCP=${VAL}/" "$CFG"
else
  echo "ETH_CAMERA_DHCP=${VAL}" >> "$CFG"
fi

/usr/local/bin/ldrs-clear-camera-config.sh

if ! systemctl restart ldrs-network.service; then
  echo "ldrs-network.service failed" >&2
  exit 1
fi

systemctl restart ldrs-camera-discovery.service 2>/dev/null || true

if [[ -f /etc/sportassist/system.env ]]; then
  # shellcheck disable=SC1091
  source /etc/sportassist/system.env
  /usr/local/bin/ldrs-hdmi-activate.sh "${HDMI_OUTPUT_MODE:-delayed}" 2>/dev/null || true
else
  systemctl restart ldrs-replay-buffer.service 2>/dev/null || true
fi

/usr/local/bin/ldrs-ensure-ssh-reachable.sh 2>/dev/null || true
echo "ETH_CAMERA_DHCP=${VAL}"
