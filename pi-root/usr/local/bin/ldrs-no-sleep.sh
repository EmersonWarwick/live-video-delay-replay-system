#!/usr/bin/env bash
# Keep the Pi awake: no console blanking; ensure boot firmware disables blanking after reboot.
set -euo pipefail

if command -v setterm >/dev/null 2>&1; then
  for tty in /dev/tty[0-9]*; do
    setterm -term linux -blank 0 -powerdown 0 -powersave off <"$tty" >/dev/null 2>&1 || true
  done
fi

CMDLINE=/boot/firmware/cmdline.txt
if [[ -f "$CMDLINE" ]] && ! grep -qE '(^| )consoleblank=0($| )' "$CMDLINE"; then
  sed -i 's/$/ consoleblank=0/' "$CMDLINE"
fi

CONFIG=/boot/firmware/config.txt
if [[ -f "$CONFIG" ]]; then
  if grep -qE '^hdmi_blanking=' "$CONFIG"; then
    sed -i 's/^hdmi_blanking=.*/hdmi_blanking=0/' "$CONFIG"
  elif ! grep -qE '^# sport-assist — keep HDMI active' "$CONFIG"; then
    tee -a "$CONFIG" >/dev/null <<'EOF'

# sport-assist — keep HDMI active (coach monitor)
hdmi_blanking=0
EOF
  fi
fi
