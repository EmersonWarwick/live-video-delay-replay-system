#!/usr/bin/env bash
# Apply HDMI_RESOLUTION_MODE — cmdline video= param (boot) + best-effort runtime mode set.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

SYSTEM_ENV=/etc/sportassist/system.env
CMDLINE=/boot/firmware/cmdline.txt
[[ -f "$CMDLINE" ]] || CMDLINE=/boot/cmdline.txt
CONNECTOR="${HDMI_CONNECTOR:-HDMI-A-1}"
FORCE_VIDEO="video=${CONNECTOR}:3840x2160M@60"

MODE=auto
if [[ -f "$SYSTEM_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$SYSTEM_ENV"
fi
MODE="${HDMI_RESOLUTION_MODE:-auto}"
if [[ "$MODE" != "auto" && "$MODE" != "force_4k" ]]; then
  MODE=auto
fi

read_cmdline() {
  tr '\n' ' ' < "$CMDLINE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

strip_hdmi_video_tokens() {
  sed -E 's/(^|[[:space:]])video=HDMI-A-[12]:[^[:space:]]+//g' \
    | sed -E 's/[[:space:]]+/ /g' \
    | sed -E 's/^ //;s/ $//'
}

write_cmdline() {
  local line="$1"
  local tmp
  tmp="$(mktemp)"
  printf '%s\n' "$line" >"$tmp"
  install -m 644 -o root -g root "$tmp" "$CMDLINE"
  rm -f "$tmp"
}

patch_cmdline() {
  local line
  line="$(read_cmdline | strip_hdmi_video_tokens)"
  if [[ "$MODE" == "force_4k" ]]; then
    if [[ -n "$line" ]]; then
      line="${line} ${FORCE_VIDEO}"
    else
      line="$FORCE_VIDEO"
    fi
  fi
  write_cmdline "$line"
}

apply_runtime() {
  local applied=0

  if command -v wlr-randr >/dev/null 2>&1; then
    if [[ "$MODE" == "force_4k" ]]; then
      for rate in 60.00 59.94 50.00 30.00; do
        if wlr-randr --output "$CONNECTOR" --mode "3840x2160@${rate}" 2>/dev/null; then
          applied=1
          break
        fi
      done
    else
      if wlr-randr --output "$CONNECTOR" --preferred 2>/dev/null \
        || wlr-randr --output "$CONNECTOR" --auto 2>/dev/null; then
        applied=1
      fi
    fi
  fi

  if [[ "$applied" -eq 0 ]] && command -v xrandr >/dev/null 2>&1; then
    export DISPLAY="${DISPLAY:-:0}"
    local out=""
    out="$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')" || true
    if [[ -n "$out" ]]; then
      if [[ "$MODE" == "force_4k" ]]; then
        if xrandr --output "$out" --mode 3840x2160 2>/dev/null; then
          applied=1
        fi
      else
        if xrandr --output "$out" --auto 2>/dev/null; then
          applied=1
        fi
      fi
    fi
  fi

  return $(( applied == 0 ))
}

patch_cmdline
runtime_ok=0
apply_runtime && runtime_ok=1 || true

echo "HDMI_RESOLUTION_MODE=${MODE} runtime_applied=${runtime_ok}"
