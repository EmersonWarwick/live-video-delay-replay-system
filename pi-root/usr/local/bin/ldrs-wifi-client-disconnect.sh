#!/usr/bin/env bash
# Disconnect wlan0 client Wi-Fi (wpa_supplicant) — wlan0 only.
set -euo pipefail

IFACE="${1:-wlan0}"
if ! iw dev "$IFACE" info &>/dev/null; then
  IFACE=$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')
fi
[[ -n "$IFACE" ]] || exit 0

pkill -f "wpa_supplicant.*${IFACE}" 2>/dev/null || true
systemctl stop "wpa_supplicant@${IFACE}.service" 2>/dev/null || true
dhclient -r "$IFACE" 2>/dev/null || true
nmcli dev disconnect "$IFACE" 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
echo "wlan client disconnected on ${IFACE}"
