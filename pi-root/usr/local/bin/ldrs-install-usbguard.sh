#!/usr/bin/env bash
# USBGuard — allowlist USB devices present at install time (Pi hubs + anything attached).
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

FALLBACK=/etc/usbguard/ldrs-rules-fallback.conf
DAEMON_CFG=/etc/usbguard/ldrs-usbguard-daemon.conf
RULES=/etc/usbguard/rules.conf

if ! dpkg -s usbguard >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y usbguard
fi

[[ -f "$DAEMON_CFG" ]] || { echo "Missing $DAEMON_CFG" >&2; exit 1; }
install -m 600 "$DAEMON_CFG" /etc/usbguard/usbguard-daemon.conf

echo "Generating USBGuard policy from connected USB devices…"
TMP=$(mktemp)
if usbguard generate-policy --no-hash >"$TMP" 2>/dev/null; then
  sed -E 's/ with-connect-type "[^"]*"//g' "$TMP" >"${TMP}.clean"
  grep -q '^block$' "${TMP}.clean" || echo 'block' >>"${TMP}.clean"
  install -m 600 "${TMP}.clean" "$RULES"
  rm -f "$TMP" "${TMP}.clean"
  echo "USBGuard policy installed from live USB topology ($(grep -c '^allow' "$RULES" || echo 0) allow rules)"
else
  rm -f "$TMP"
  echo "usbguard generate-policy failed — using fallback rules" >&2
  [[ -f "$FALLBACK" ]] || { echo "Missing $FALLBACK" >&2; exit 1; }
  install -m 600 "$FALLBACK" "$RULES"
fi

systemctl enable usbguard.service 2>/dev/null || true

# Do not restart usbguard during boot: ldrs-usb-hardening.service has Before=usbguard.service,
# so systemctl restart here deadlocks (oneshot blocks usbguard from ever starting).
if systemctl is-active --quiet usbguard.service 2>/dev/null \
  || systemctl is-active --quiet usbguard-daemon.service 2>/dev/null; then
  systemctl restart usbguard.service 2>/dev/null \
    || systemctl restart usbguard-daemon.service 2>/dev/null || true
fi

if systemctl is-active --quiet usbguard.service 2>/dev/null \
  || systemctl is-active --quiet usbguard-daemon.service 2>/dev/null; then
  echo "USBGuard active"
elif ! systemctl is-active --quiet ldrs-usb-hardening.service 2>/dev/null; then
  echo "USBGuard rules installed — systemd will start usbguard after hardening completes"
else
  echo "USBGuard install finished but service not active — check: journalctl -u usbguard -n 30" >&2
  exit 1
fi

mkdir -p /var/lib/sportassist
touch /var/lib/sportassist/usbguard-configured
