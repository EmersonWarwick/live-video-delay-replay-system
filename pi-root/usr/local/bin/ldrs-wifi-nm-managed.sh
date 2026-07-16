#!/usr/bin/env bash
# Toggle NetworkManager management of USB wlan0 only — never reload NM (eth0 stays up).
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ACTION="${1:-}"
CONF=/etc/NetworkManager/conf.d/ldrs-unmanaged-wlan0.conf
LEGACY=/etc/NetworkManager/conf.d/unmanaged-wlan0.conf
BACKUP=/etc/NetworkManager/conf.d/ldrs-unmanaged-wlan0.conf.bak
LEGACY_BACKUP=/etc/NetworkManager/conf.d/unmanaged-wlan0.conf.bak
IFACE="${2:-wlan0}"

resolve_iface() {
  if iw dev "$IFACE" info &>/dev/null; then
    echo "$IFACE"
    return 0
  fi
  iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}'
}

IFACE="$(resolve_iface || true)"
if [[ -z "$IFACE" ]]; then
  echo "No wlan interface" >&2
  exit 1
fi

case "$ACTION" in
  enable)
    if [[ -f "$CONF" ]]; then
      mv "$CONF" "$BACKUP"
    fi
    if [[ -f "$LEGACY" ]]; then
      mv "$LEGACY" "$LEGACY_BACKUP"
    fi
    sleep 1
    iw dev "$IFACE" set type managed 2>/dev/null || true
    ip addr flush dev "$IFACE" 2>/dev/null || true
    ip link set "$IFACE" up 2>/dev/null || true
    nmcli dev set "$IFACE" managed yes 2>/dev/null || true
    rfkill unblock wifi 2>/dev/null || true
    echo "NetworkManager managing ${IFACE}"
    ;;
  disable)
    if [[ -f "$BACKUP" ]]; then
      mv "$BACKUP" "$CONF"
    elif [[ ! -f "$CONF" ]]; then
      cat >"$CONF" <<EOF
[keyfile]
unmanaged-devices=interface-name:${IFACE}

[device]
wifi.scan-rand-mac-address=no
EOF
    fi
    if [[ -f "$LEGACY_BACKUP" ]]; then
      mv "$LEGACY_BACKUP" "$LEGACY"
    elif [[ ! -f "$LEGACY" ]]; then
      cat >"$LEGACY" <<EOF
[device]
wifi.scan-rand-mac-address=no

[keyfile]
unmanaged-devices=interface-name:${IFACE}
EOF
    fi
    nmcli dev disconnect "$IFACE" 2>/dev/null || true
    nmcli dev set "$IFACE" managed no 2>/dev/null || true
    echo "NetworkManager not managing ${IFACE}"
    ;;
  *)
    echo "usage: ldrs-wifi-nm-managed.sh enable|disable [iface]" >&2
    exit 2
    ;;
esac
