#!/usr/bin/env bash
# Wi-Fi AP diagnostics — run on the Pi (console or SSH). See build-instructions-mac.md.
set -euo pipefail

echo "=== Sport Assist Wi-Fi AP diagnostics ==="
echo

echo "-- Services --"
systemctl is-active ldrs-wifi-ap.service hostapd dnsmasq NetworkManager 2>&1 || true
systemctl is-enabled ldrs-wifi-ap.service hostapd 2>&1 || true
echo

echo "-- wifi-ap.env --"
if [[ -f /etc/sportassist/wifi-ap.env ]]; then
  grep -E '^AP_(SSID|PSK|INTERFACE|COUNTRY)' /etc/sportassist/wifi-ap.env | sed 's/AP_PSK=.*/AP_PSK=(redacted)/'
else
  echo "MISSING /etc/sportassist/wifi-ap.env"
fi
echo

echo "-- Wireless interfaces --"
rfkill list
iw dev 2>&1 || echo "iw: no wireless"
echo
for iface in $(iw dev 2>/dev/null | awk '/^\s+Interface/ {print $2}'); do
  driver=$(basename "$(readlink -f "/sys/class/net/${iface}/device/driver" 2>/dev/null)" 2>/dev/null || echo "?")
  echo "-- ${iface} (driver ${driver}) --"
  ip -br addr show "$iface" 2>&1 || true
  iw dev "$iface" info 2>&1 || true
  if command -v nmcli >/dev/null 2>&1; then
    nmcli -f GENERAL.STATE,GENERAL.CONNECTION dev show "$iface" 2>&1 || true
  fi
  echo
done

echo "-- hostapd config --"
if [[ -f /etc/hostapd/hostapd.conf ]]; then
  grep -E '^(interface|ssid|country_code|channel)=' /etc/hostapd/hostapd.conf
else
  echo "MISSING /etc/hostapd/hostapd.conf"
fi
if [[ ! -f /etc/hostapd/hostapd-sportassist.conf ]]; then
  echo "MISSING /etc/hostapd/hostapd-sportassist.conf (re-extract pi-root)"
fi
echo

echo "-- dnsmasq AP scope (wlan0 — only when AP is active) --"
if [[ -f /etc/dnsmasq.d/sportassist-wifi-ap.conf ]]; then
  grep -E '^interface=|^dhcp-range=' /etc/dnsmasq.d/sportassist-wifi-ap.conf
else
  echo "AP dnsmasq conf absent (expected in client Wi-Fi mode)"
fi
echo

echo "-- dnsmasq eth0 camera scope --"
if [[ -L /etc/dnsmasq.d/ldrs-camera-eth.enabled.conf ]]; then
  grep -E '^interface=|^dhcp-range=' /etc/dnsmasq.d/ldrs-camera-eth.conf
else
  echo "eth0 camera DHCP disabled (ETH_CAMERA_DHCP=0)"
fi
echo

echo "-- Built-in Wi-Fi (required for AP) --"
CFG=/boot/firmware/config.txt
[[ -f "$CFG" ]] || CFG=/boot/config.txt
if grep -qE 'disable-wifi-pi5|^[[:space:]]*dtoverlay=disable-wifi([[:space:]]|$)' "$CFG" 2>/dev/null; then
  echo "WARNING: onboard Wi-Fi disable overlay present in $CFG — remove and reboot"
  grep -E 'disable-wifi-pi5|^[[:space:]]*dtoverlay=disable-wifi([[:space:]]|$)' "$CFG" 2>/dev/null || true
else
  echo "No disable-wifi overlay in $CFG (OK)"
fi
for iface in $(iw dev 2>/dev/null | awk '/Interface/ {print $2}'); do
  driver=$(basename "$(readlink -f "/sys/class/net/${iface}/device/driver" 2>/dev/null)" 2>/dev/null || echo "?")
  if [[ "$driver" == "brcmfmac" ]]; then
    echo "Built-in radio: ${iface} (${driver})"
  fi
done
echo

echo "-- Recent logs --"
journalctl -u ldrs-wifi-ap.service -b -n 20 --no-pager 2>&1 || true
journalctl -u hostapd -b -n 20 --no-pager 2>&1 || true
journalctl -u dnsmasq -b -n 15 --no-pager 2>&1 || true
echo

echo "-- eth0 (SSH via router only before ldrs-network) --"
ip -br addr show eth0 2>&1 || true
systemctl is-active ldrs-network.service 2>&1 || true
echo

echo "-- USB hardening --"
systemctl is-active usbguard.service 2>&1 || systemctl is-active usbguard-daemon.service 2>&1 || true
systemctl is-enabled ldrs-usb-hardening.service 2>&1 || true
if command -v rpi-eeprom-config >/dev/null 2>&1; then
  rpi-eeprom-config 2>/dev/null | grep '^BOOT_ORDER=' || true
fi
if command -v usbguard >/dev/null 2>&1; then
  usbguard list-devices 2>&1 | head -20 || true
fi
echo

echo "To retry AP setup: sudo systemctl restart ldrs-wifi-ap.service"
echo "If hostapd fails: sudo hostapd -dd /etc/hostapd/hostapd.conf"
