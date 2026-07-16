#!/usr/bin/env bash
# Ethernet camera network — eth0 only (never touches wlan0). See spec-network-dhcp.md
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

CFG=/etc/sportassist/network.env
ETH_DHCP_CONF=/etc/dnsmasq.d/ldrs-camera-eth.conf
ETH_DHCP_LINK=/etc/dnsmasq.d/ldrs-camera-eth.enabled.conf
PI_INTERFACE="${PI_INTERFACE:-eth0}"

[[ -f "$CFG" ]] || { echo "Missing $CFG" >&2; exit 2; }
# shellcheck disable=SC1090
source "$CFG"

: "${PI_INTERFACE:=eth0}"
: "${PI_STATIC_IP:=192.168.10.1}"

if ip link show "$PI_INTERFACE" &>/dev/null; then
  if command -v nmcli >/dev/null 2>&1; then
    nmcli dev disconnect "$PI_INTERFACE" 2>/dev/null || true
    nmcli dev set "$PI_INTERFACE" managed no 2>/dev/null || true
  fi
  dhclient -r "$PI_INTERFACE" 2>/dev/null || true
  pkill -f "dhclient.*${PI_INTERFACE}" 2>/dev/null || true
  dhcpcd -k "$PI_INTERFACE" 2>/dev/null || true
  ip -4 addr flush dev "$PI_INTERFACE" 2>/dev/null || true
  if [[ "${ETH_CAMERA_DHCP:-1}" == "1" ]]; then
    ip addr add "${PI_STATIC_IP}/24" dev "$PI_INTERFACE"
    ip link set "$PI_INTERFACE" up
  else
    ip link set "$PI_INTERFACE" up
    if command -v dhcpcd >/dev/null 2>&1; then
      dhcpcd -1 -4 -t 25 "$PI_INTERFACE" 2>/dev/null || true
      if [[ -z "$(ip -4 -br addr show "$PI_INTERFACE" | awk '{print $3}')" ]]; then
        sleep 2
        dhcpcd -1 -4 -t 25 "$PI_INTERFACE" 2>/dev/null || true
      fi
    elif command -v dhclient >/dev/null 2>&1; then
      dhclient -1 -timeout 25 "$PI_INTERFACE" 2>/dev/null || true
    elif command -v nmcli >/dev/null 2>&1; then
      nmcli dev set "$PI_INTERFACE" managed yes 2>/dev/null || true
      nmcli dev connect "$PI_INTERFACE" 2>/dev/null || true
    fi
  fi
fi

if [[ "${ETH_CAMERA_DHCP:-1}" == "1" ]]; then
  ln -sf "$ETH_DHCP_CONF" "$ETH_DHCP_LINK"
else
  rm -f "$ETH_DHCP_LINK"
fi

if systemctl is-active --quiet dnsmasq 2>/dev/null; then
  kill -HUP "$(pidof dnsmasq)" 2>/dev/null || systemctl reload dnsmasq 2>/dev/null || systemctl restart dnsmasq 2>/dev/null || true
else
  if ! systemctl start dnsmasq 2>/dev/null; then
    echo "dnsmasq failed to start for eth0 camera DHCP — check journalctl -u dnsmasq" >&2
    journalctl -u dnsmasq -b -n 10 --no-pager >&2 || true
  fi
fi

/usr/local/bin/ldrs-ensure-ssh-reachable.sh 2>/dev/null || true
echo "Network eth0 mode ETH_CAMERA_DHCP=${ETH_CAMERA_DHCP:-1}"
