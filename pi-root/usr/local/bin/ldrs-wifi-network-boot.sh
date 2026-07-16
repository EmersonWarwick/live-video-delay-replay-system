#!/usr/bin/env bash
# Boot-time Wi-Fi orchestration — AP or client building Wi-Fi with fallback.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN_DIR=/run/sportassist
mkdir -p "$RUN_DIR"

# Ensure default config exists
if [[ ! -f /etc/sportassist/wifi-network.env ]]; then
  cat >/etc/sportassist/wifi-network.env <<'EOF'
# Sport Assist Wi-Fi network mode
USE_LOCAL_ACCESS_POINT=1
DEVICE_HOSTNAME=sport-assist.local
CLIENT_WIFI_SSID=
CLIENT_WIFI_USERNAME=
CLIENT_WIFI_PASSWORD=
CLIENT_WIFI_SECURITY_TYPE=wpa2-psk
FALLBACK_TIMEOUT_SECONDS=90
EOF
  chmod 640 /etc/sportassist/wifi-network.env
  chown root:sportassist /etc/sportassist/wifi-network.env 2>/dev/null || true
fi

/usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/network_cli.py boot
rc=$?
# Camera ingest is always on eth0 — ensure dnsmasq is not blocked by stale wlan0 AP config.
/usr/local/bin/ldrs-network.sh 2>/dev/null || true
exit "$rc"
