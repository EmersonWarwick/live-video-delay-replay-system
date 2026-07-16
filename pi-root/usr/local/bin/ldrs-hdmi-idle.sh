#!/usr/bin/env bash
# HDMI idle: pre-composited splash (logo 50% height + title) — works with mpv or cvlc.
set -euo pipefail

SYSTEM_ENV=/etc/sportassist/system.env
if [[ -f "$SYSTEM_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$SYSTEM_ENV"
fi
[[ "${HDMI_ENABLED:-1}" == "1" ]] || exit 0

/usr/local/bin/ldrs-build-idle-splash.sh

SPLASH=/var/lib/sportassist/SportAssistIdle.png
[[ -f "$SPLASH" ]] || { echo "Missing $SPLASH" >&2; exit 1; }

export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

if command -v mpv >/dev/null 2>&1; then
  exec mpv \
    --no-config \
    --no-terminal \
    --really-quiet \
    --fs \
    --no-border \
    --keep-open=always \
    --loop-file=inf \
    --image-display-duration=inf \
    --no-audio \
    --no-osc \
    --no-input-default-bindings \
    "$SPLASH"
fi

if command -v cvlc >/dev/null 2>&1; then
  exec cvlc \
    --intf dummy \
    --no-video-title-show \
    --no-osd \
    --fullscreen \
    --loop \
    --no-audio \
    "$SPLASH"
fi

echo "Neither mpv nor cvlc found" >&2
exit 1
