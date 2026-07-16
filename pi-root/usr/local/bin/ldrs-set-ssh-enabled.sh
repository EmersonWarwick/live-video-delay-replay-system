#!/usr/bin/env bash
# Set SSH_ENABLED — enable or disable sshd on eth0 and wlan0
set -euo pipefail

CFG=/etc/sportassist/system.env
ENABLED="${1:-}"

if [[ ! -f "$CFG" ]]; then
  echo "Missing $CFG" >&2
  exit 2
fi

if [[ "$ENABLED" != "0" && "$ENABLED" != "1" ]]; then
  echo "SSH enabled must be 0 or 1" >&2
  exit 1
fi

cp -a "$CFG" "${CFG}.bak"
if grep -q '^SSH_ENABLED=' "$CFG"; then
  sed -i "s/^SSH_ENABLED=.*/SSH_ENABLED=${ENABLED}/" "$CFG"
else
  echo "SSH_ENABLED=${ENABLED}" >> "$CFG"
fi

ssh_unit() {
  if systemctl list-unit-files ssh.service &>/dev/null; then
    echo ssh
  elif systemctl list-unit-files sshd.service &>/dev/null; then
    echo sshd
  else
    echo ssh
  fi
}

UNIT="$(ssh_unit)"
if [[ "$ENABLED" == "1" ]]; then
  systemctl enable "$UNIT" 2>/dev/null || true
  systemctl start "$UNIT" 2>/dev/null || true
else
  systemctl stop "$UNIT" 2>/dev/null || true
  systemctl disable "$UNIT" 2>/dev/null || true
fi

/usr/local/bin/ldrs-ensure-ssh-reachable.sh 2>/dev/null || true
echo "SSH_ENABLED=${ENABLED}"
