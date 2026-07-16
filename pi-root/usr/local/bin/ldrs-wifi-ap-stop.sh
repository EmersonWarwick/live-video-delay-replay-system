#!/usr/bin/env bash
# Stop Wi-Fi AP — hostapd only by default (keeps dnsmasq/eth0 untouched for SSH).
# Usage: ldrs-wifi-ap-stop.sh [hostapd-only|full]
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

MODE="${1:-hostapd-only}"
CFG=/etc/sportassist/wifi-ap.env
AP_INTERFACE=""

if [[ -f "$CFG" ]]; then
  # shellcheck disable=SC1090
  source "$CFG"
fi

driver_for_iface() {
  local iface="$1"
  basename "$(readlink -f "/sys/class/net/${iface}/device/driver" 2>/dev/null)" 2>/dev/null || true
}

resolve_ap_interface() {
  local configured="${AP_INTERFACE:-}"
  if [[ -n "$configured" ]] && iw dev "$configured" info &>/dev/null; then
    echo "$configured"
    return 0
  fi
  local iface driver
  while read -r iface; do
    [[ -z "$iface" ]] && continue
    driver=$(driver_for_iface "$iface")
    if [[ "$driver" == "brcmfmac" ]]; then
      echo "$iface"
      return 0
    fi
  done < <(iw dev 2>/dev/null | awk '/Interface/ {print $2}')
  iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}'
}

AP_INTERFACE="$(resolve_ap_interface || true)"
DNSMASQ_AP=/etc/dnsmasq.d/sportassist-wifi-ap.conf
ETH_DHCP_LINK=/etc/dnsmasq.d/ldrs-camera-eth.enabled.conf

systemctl stop hostapd 2>/dev/null || true
rm -f "$DNSMASQ_AP"

if [[ "$MODE" == "full" ]]; then
  systemctl stop dnsmasq 2>/dev/null || true
elif [[ -f "$ETH_DHCP_LINK" ]]; then
  systemctl reload dnsmasq 2>/dev/null || systemctl restart dnsmasq 2>/dev/null || systemctl start dnsmasq 2>/dev/null || true
elif systemctl is-active --quiet dnsmasq 2>/dev/null; then
  systemctl stop dnsmasq 2>/dev/null || true
fi

if [[ -n "${AP_INTERFACE:-}" ]]; then
  if command -v iptables >/dev/null 2>&1; then
    iptables -t nat -D PREROUTING -i "${AP_INTERFACE}" -p tcp --dport 80 -j REDIRECT --to-port 8080 2>/dev/null || true
  fi
  ip addr flush dev "${AP_INTERFACE}" 2>/dev/null || true
  if command -v nmcli >/dev/null 2>&1; then
    nmcli dev disconnect "${AP_INTERFACE}" 2>/dev/null || true
  fi
fi

echo "Wi-Fi AP stopped (${MODE})"
