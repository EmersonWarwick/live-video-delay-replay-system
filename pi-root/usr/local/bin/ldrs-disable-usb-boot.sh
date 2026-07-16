#!/usr/bin/env bash
# Disable USB mass-storage boot in Pi EEPROM — SD card only (0xf1).
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v rpi-eeprom-config >/dev/null 2>&1; then
  echo "rpi-eeprom-config not found — skip EEPROM USB boot disable" >&2
  exit 0
fi

# Read right-to-left: 1 = SD card, f = restart loop. No 4 = USB-MSD boot.
TARGET_BOOT_ORDER=0xf1

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
rpi-eeprom-config >"$TMP"

CURRENT=$(grep -E '^BOOT_ORDER=' "$TMP" | head -1 | cut -d= -f2- | tr -d '[:space:]' || true)
if [[ "$CURRENT" == "$TARGET_BOOT_ORDER" ]]; then
  echo "BOOT_ORDER already ${TARGET_BOOT_ORDER} (USB MSD boot disabled)"
  exit 0
fi

if grep -q '^BOOT_ORDER=' "$TMP"; then
  sed -i "s/^BOOT_ORDER=.*/BOOT_ORDER=${TARGET_BOOT_ORDER}/" "$TMP"
else
  printf '\nBOOT_ORDER=%s\n' "$TARGET_BOOT_ORDER" >>"$TMP"
fi

rpi-eeprom-config --apply "$TMP" >/dev/null
echo "EEPROM: BOOT_ORDER=${TARGET_BOOT_ORDER} (SD card only — USB mass-storage boot disabled)"
echo "Reboot once for the EEPROM update to take effect."
