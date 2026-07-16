#!/usr/bin/env bash
# Ensure Pi 5 onboard Wi‑Fi is available for the venue AP (remove disable overlays).
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

CFG=/boot/firmware/config.txt
[[ -f "$CFG" ]] || CFG=/boot/config.txt

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 1
fi

changed=0
for overlay in disable-wifi-pi5 disable-wifi; do
  if grep -qE "^[[:space:]]*dtoverlay=${overlay}([[:space:]]|$)" "$CFG" 2>/dev/null; then
    sed -i "/^[[:space:]]*dtoverlay=${overlay}[[:space:]]*$/d" "$CFG"
    echo "Removed dtoverlay=${overlay} from $CFG"
    changed=1
  fi
done

rfkill unblock wifi 2>/dev/null || true

echo "Onboard Wi‑Fi overlays cleared (AP uses Raspberry Pi built-in radio)."
if [[ "$changed" -eq 1 ]]; then
  echo "Reboot required for dtoverlay changes to take full effect."
fi
