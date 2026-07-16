#!/usr/bin/env bash
# Apply eth0 camera network when Direct to Pi is on but eth0 is not yet 192.168.10.1
set -euo pipefail

CFG=/etc/sportassist/network.env
[[ -f "$CFG" ]] || exit 0
# shellcheck disable=SC1090
source "$CFG"

[[ "${ETH_CAMERA_DHCP:-1}" == "1" ]] || exit 0

IFACE="${PI_INTERFACE:-eth0}"
PI_IP="${PI_STATIC_IP:-192.168.10.1}"

cur="$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}' | head -1 | cut -d/ -f1 || true)"
if [[ "$cur" == "$PI_IP" ]]; then
  exit 0
fi

exec /usr/local/bin/ldrs-network.sh
