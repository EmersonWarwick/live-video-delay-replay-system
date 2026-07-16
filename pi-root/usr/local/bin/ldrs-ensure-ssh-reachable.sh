#!/usr/bin/env bash
# Keep sshd up and record SSH endpoints on eth0 and wlan0. Never reconfigure the other interface.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN=/run/sportassist
mkdir -p "$RUN"

iface_ipv4() {
  local dev="$1"
  ip -4 -br addr show "$dev" 2>/dev/null | awk '{print $3}' | cut -d/ -f1 | head -1
}

ensure_sshd() {
  if systemctl is-active --quiet ssh 2>/dev/null; then
    return 0
  fi
  if systemctl is-active --quiet sshd 2>/dev/null; then
    return 0
  fi
  systemctl start ssh 2>/dev/null || systemctl start sshd 2>/dev/null || true
}

stop_sshd() {
  systemctl stop ssh 2>/dev/null || systemctl stop sshd 2>/dev/null || true
}

SSH_ENABLED=1
if [[ -f /etc/sportassist/system.env ]]; then
  # shellcheck disable=SC1091
  source /etc/sportassist/system.env
  SSH_ENABLED="${SSH_ENABLED:-1}"
fi

if [[ "$SSH_ENABLED" == "1" ]]; then
  ensure_sshd
else
  stop_sshd
fi

sshd_active=0
if systemctl is-active --quiet ssh 2>/dev/null || systemctl is-active --quiet sshd 2>/dev/null; then
  sshd_active=1
fi

# Customer LAN on eth0: retry DHCP if cable is up but no address yet.
if [[ -f /etc/sportassist/network.env ]]; then
  # shellcheck disable=SC1091
  source /etc/sportassist/network.env
  if [[ "${ETH_CAMERA_DHCP:-1}" == "0" ]]; then
    eth_ip_now=$(iface_ipv4 eth0)
    if [[ -z "$eth_ip_now" ]] && ip link show eth0 2>/dev/null | grep -q "LOWER_UP"; then
      if command -v dhcpcd >/dev/null 2>&1; then
        dhcpcd -1 -4 -t 25 eth0 2>/dev/null || true
      fi
    fi
  fi
fi

eth_ip=$(iface_ipv4 eth0)
wlan_ip=$(iface_ipv4 wlan0)
ap_active=0
ap_ip=""
if systemctl is-active --quiet hostapd 2>/dev/null; then
  ap_active=1
  ap_ip=$(iface_ipv4 wlan0)
  [[ -z "$ap_ip" ]] && ap_ip="192.168.4.1"
fi

eth_ssh=0
[[ -n "$eth_ip" && "$sshd_active" == "1" ]] && eth_ssh=1
wlan_ssh=0
[[ -n "$wlan_ip" && "$sshd_active" == "1" ]] && wlan_ssh=1

/usr/local/bin/ldrs-python3.sh - "$eth_ip" "$wlan_ip" "$ap_active" "$ap_ip" "$eth_ssh" "$wlan_ssh" "$sshd_active" <<'PY'
import json, sys
from pathlib import Path
eth_ip, wlan_ip, ap_active, ap_ip, eth_ssh, wlan_ssh, sshd_active = sys.argv[1:8]
sshd_on = sshd_active == "1"
out = {
    "sshdActive": sshd_on,
    "hostname": "sport-assist.local",
    "eth0": {
        "ip": eth_ip,
        "sshAvailable": eth_ssh == "1",
        "hint": "ssh sportassist@{}".format(eth_ip) if eth_ip and sshd_on else (
            "SSH disabled in Settings" if not sshd_on else
            "ssh sportassist@192.168.10.1 (Direct/PoE mode)"
        ),
    },
    "wlan0": {
        "ip": wlan_ip,
        "sshAvailable": wlan_ssh == "1",
        "apActive": ap_active == "1",
        "apIp": ap_ip,
        "hint": "ssh sportassist@{}".format(wlan_ip) if wlan_ip and sshd_on else (
            "ssh sportassist@{} (AP mode)".format(ap_ip) if ap_ip and sshd_on else (
                "SSH disabled in Settings" if not sshd_on else ""
            )
        ),
    },
}
path = Path("/run/sportassist/ssh-endpoints.json")
path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(json.dumps(out))
PY
