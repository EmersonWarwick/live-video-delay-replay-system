#!/usr/bin/env bash
# Apply mDNS hostname via Avahi — sport-assist.local
set -euo pipefail

HOST="${1:-sport-assist.local}"
BARE="${HOST%.local}"

echo "$BARE" >/etc/hostname
hostnamectl set-hostname "$BARE" 2>/dev/null || hostname "$BARE" 2>/dev/null || true

if [[ -f /etc/avahi/avahi-daemon.conf ]]; then
  if grep -q '^host-name=' /etc/avahi/avahi-daemon.conf; then
    sed -i "s/^host-name=.*/host-name=${BARE}/" /etc/avahi/avahi-daemon.conf
  else
    echo "host-name=${BARE}" >>/etc/avahi/avahi-daemon.conf
  fi
fi

if ! grep -q "127.0.1.1.*${BARE}" /etc/hosts 2>/dev/null; then
  echo -e "127.0.1.1\t${BARE}" >>/etc/hosts
fi

systemctl enable avahi-daemon 2>/dev/null || true
systemctl restart avahi-daemon 2>/dev/null || true

echo "Hostname set: ${BARE}.local"
