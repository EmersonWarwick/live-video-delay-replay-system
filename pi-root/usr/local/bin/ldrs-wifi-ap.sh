#!/usr/bin/env bash
# Start always-on Wi‑Fi AP on the Pi built-in radio — see .cursor/spec-wifi-ap.md
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

CFG=/etc/sportassist/wifi-ap.env
HOSTAPD_CFG=/etc/hostapd/hostapd-sportassist.conf
DNSMASQ_AP=/etc/dnsmasq.d/sportassist-wifi-ap.conf

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 2
fi
# shellcheck disable=SC1090
source "$CFG"

: "${AP_SSID:?AP_SSID required}"
: "${AP_PSK:?AP_PSK required}"
: "${AP_ADDRESS:=192.168.4.1}"
: "${AP_COUNTRY_CODE:=GB}"
: "${AP_CHANNEL:=6}"
: "${AP_NETMASK:=255.255.255.0}"
: "${AP_DHCP_RANGE_START:=192.168.4.100}"
: "${AP_DHCP_RANGE_END:=192.168.4.150}"
: "${AP_DHCP_LEASE_TIME:=24h}"

driver_for_iface() {
  local iface="$1"
  basename "$(readlink -f "/sys/class/net/${iface}/device/driver" 2>/dev/null)" 2>/dev/null || true
}

list_wlan_ifaces() {
  iw dev 2>/dev/null | awk '/Interface/ {print $2}'
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
  done < <(list_wlan_ifaces)

  local count
  count=$(list_wlan_ifaces | wc -l | tr -d ' ')
  if [[ "$count" -eq 1 ]]; then
    list_wlan_ifaces
    return 0
  fi

  echo "No Raspberry Pi built-in Wi‑Fi interface found (brcmfmac)." >&2
  echo "Remove dtoverlay=disable-wifi-pi5 from /boot/firmware/config.txt if present, then reboot." >&2
  list_wlan_ifaces | while read -r iface; do
    echo "  ${iface}: driver $(driver_for_iface "$iface")" >&2
  done
  return 1
}

/usr/local/bin/ldrs-ensure-builtin-wifi.sh 2>/dev/null || true

AP_INTERFACE="$(resolve_ap_interface)"

echo "Configuring Wi‑Fi AP on ${AP_INTERFACE} (${AP_SSID})"

if [[ ! -f "$HOSTAPD_CFG" ]]; then
  echo "Missing hostapd template: $HOSTAPD_CFG (re-extract pi-root)" >&2
  exit 2
fi

systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
sleep 1

rfkill unblock wifi || true
raspi-config nonint do_wifi_country "${AP_COUNTRY_CODE}" || true

if command -v nmcli >/dev/null 2>&1; then
  /usr/local/bin/ldrs-wifi-nm-managed.sh disable "${AP_INTERFACE}" 2>/dev/null || true
  nmcli dev disconnect "${AP_INTERFACE}" 2>/dev/null || true
fi
systemctl stop "wpa_supplicant@${AP_INTERFACE}.service" 2>/dev/null || true

sed -e "s/^ssid=.*/ssid=${AP_SSID}/" \
    -e "s/^wpa_passphrase=.*/wpa_passphrase=${AP_PSK}/" \
    -e "s/^country_code=.*/country_code=${AP_COUNTRY_CODE}/" \
    -e "s/^channel=.*/channel=${AP_CHANNEL}/" \
    -e "s/^interface=.*/interface=${AP_INTERFACE}/" \
    "$HOSTAPD_CFG" > /etc/hostapd/hostapd.conf

grep -q '^DAEMON_CONF=' /etc/default/hostapd 2>/dev/null && \
  sed -i 's|^#*DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd || \
  echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd

cat >"$DNSMASQ_AP" <<EOF
interface=${AP_INTERFACE}
bind-interfaces

dhcp-range=${AP_DHCP_RANGE_START},${AP_DHCP_RANGE_END},${AP_NETMASK},${AP_DHCP_LEASE_TIME}
dhcp-option=3,${AP_ADDRESS}
dhcp-option=6,${AP_ADDRESS}

domain-needed
bogus-priv
EOF

ip link set "${AP_INTERFACE}" down 2>/dev/null || true
ip addr flush dev "${AP_INTERFACE}" 2>/dev/null || true
ip addr add "${AP_ADDRESS}/24" dev "${AP_INTERFACE}"
ip link set "${AP_INTERFACE}" up
sleep 1

if ! systemctl start hostapd; then
  echo "hostapd failed to start" >&2
  journalctl -u hostapd -b -n 25 --no-pager >&2 || true
  exit 1
fi

if ! systemctl start dnsmasq; then
  echo "dnsmasq failed to start (AP may still broadcast)" >&2
  journalctl -u dnsmasq -b -n 25 --no-pager >&2 || true
  exit 1
fi

if command -v iptables >/dev/null 2>&1; then
  iptables -t nat -D PREROUTING -i "${AP_INTERFACE}" -p tcp --dport 80 -j REDIRECT --to-port 8080 2>/dev/null || true
  iptables -t nat -A PREROUTING -i "${AP_INTERFACE}" -p tcp --dport 80 -j REDIRECT --to-port 8080
fi

/usr/local/bin/ldrs-ensure-ssh-reachable.sh 2>/dev/null || true
echo "Wi‑Fi AP active: SSID=${AP_SSID} address=${AP_ADDRESS} interface=${AP_INTERFACE}"
