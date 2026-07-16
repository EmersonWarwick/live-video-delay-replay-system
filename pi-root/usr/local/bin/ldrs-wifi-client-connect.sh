#!/usr/bin/env bash
# Connect USB wlan0 to building Wi-Fi via wpa_supplicant — wlan0 only; never touches eth0.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

SSID="${1:-}"
PSK="${2:-}"
SECURITY="${3:-wpa2-psk}"
IFACE="${4:-wlan0}"

if [[ -z "$SSID" ]]; then
  echo "usage: ldrs-wifi-client-connect.sh <ssid> [psk] [security] [iface]" >&2
  exit 2
fi

if ! iw dev "$IFACE" info &>/dev/null; then
  IFACE=$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}')
fi
[[ -n "$IFACE" ]] || { echo "no wlan interface" >&2; exit 1; }

/usr/local/bin/ldrs-wifi-ap-stop.sh hostapd-only
sleep 2

# Keep NetworkManager away from wlan0 — do not reload NM (eth0 stays on router DHCP).
nmcli dev set "$IFACE" managed no 2>/dev/null || true
systemctl stop "wpa_supplicant@${IFACE}.service" 2>/dev/null || true
pkill -f "wpa_supplicant.*${IFACE}" 2>/dev/null || true
dhclient -r "$IFACE" 2>/dev/null || true
dhcpcd -k "$IFACE" 2>/dev/null || true
pkill -f "dhclient.*${IFACE}" 2>/dev/null || true

iw dev "$IFACE" set type managed 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
ip link set "$IFACE" up
rfkill unblock wifi 2>/dev/null || true

WPA_CONF="/etc/wpa_supplicant/wpa_supplicant-${IFACE}-ldrs.conf"
mkdir -p /etc/wpa_supplicant
chmod 700 /etc/wpa_supplicant

if [[ "$SECURITY" == "open" ]]; then
  cat >"$WPA_CONF" <<EOF
ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB

network={
    ssid="${SSID}"
    key_mgmt=NONE
}
EOF
elif [[ "$SECURITY" == "wpa-eap" ]]; then
  USER="${PSK%%|*}"
  PASS="${PSK#*|}"
  cat >"$WPA_CONF" <<EOF
ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB

network={
    ssid="${SSID}"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="${USER}"
    password="${PASS}"
    phase2="auth=MSCHAPV2"
}
EOF
else
  cat >"$WPA_CONF" <<EOF
ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB

network={
    ssid="${SSID}"
    psk="${PSK}"
}
EOF
fi
chmod 600 "$WPA_CONF"

if ! wpa_supplicant -B -i "$IFACE" -c "$WPA_CONF" -D nl80211,wext; then
  echo "wpa_supplicant failed to start" >&2
  exit 1
fi

sleep 3
if command -v dhcpcd >/dev/null 2>&1; then
  dhcpcd -1 -4 -t 25 "$IFACE" 2>/dev/null || true
elif command -v dhclient >/dev/null 2>&1; then
  dhclient -1 -timeout 25 "$IFACE" 2>/dev/null || true
fi

for _ in $(seq 1 30); do
  if iw dev "$IFACE" link 2>/dev/null | grep -q "Connected to"; then
    if ip -4 addr show "$IFACE" | grep -q 'inet '; then
      ip -4 -br addr show "$IFACE"
      /usr/local/bin/ldrs-ensure-ssh-reachable.sh 2>/dev/null || true
      # wlan0 is for tablet streaming only — refresh eth0 camera DHCP/dnsmasq.
      /usr/local/bin/ldrs-network.sh 2>/dev/null || true
      exit 0
    fi
  fi
  sleep 2
done

echo "wifi_connect_timeout" >&2
iw dev "$IFACE" link 2>&1 || true
exit 1
