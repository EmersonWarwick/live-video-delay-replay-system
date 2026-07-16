#!/usr/bin/env bash
# Physical USB hardening — USBGuard allowlist + disable USB MSD EEPROM boot.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

STAMP=/var/lib/sportassist/usbguard-configured
if [[ "${LDRS_FORCE_USB_HARDENING:-0}" != "1" ]] && [[ -f "$STAMP" ]]; then
  if systemctl is-active --quiet usbguard.service 2>/dev/null \
    || systemctl is-active --quiet usbguard-daemon.service 2>/dev/null; then
    /usr/local/bin/ldrs-disable-usb-boot.sh
    exit 0
  fi
fi

/usr/local/bin/ldrs-install-usbguard.sh
/usr/local/bin/ldrs-disable-usb-boot.sh
echo "USB hardening applied."
