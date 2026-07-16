#!/usr/bin/env bash
# Build fullscreen idle splash — logo at 50% screen height + "Sport Assist" title.
set -euo pipefail

LOGO=/usr/share/sportassist/SportAssistLogo.png
OUT_DIR=/var/lib/sportassist
OUT="${OUT_DIR}/SportAssistIdle.png"
SYSTEM_ENV=/etc/sportassist/system.env
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
CANVAS_W=3840
CANVAS_H=2160
LOGO_MAX_H=$((CANVAS_H / 2))
FORCE=0
[[ "${1:-}" == "--force" || "${1:-}" == "-f" ]] && FORCE=1

ROTATION=0
if [[ -f "$SYSTEM_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$SYSTEM_ENV"
fi
case "${IDLE_SPLASH_ROTATION:-0}" in
  -90|0|90) ROTATION="${IDLE_SPLASH_ROTATION:-0}" ;;
  *) ROTATION=0 ;;
esac

[[ -f "$LOGO" ]] || { echo "Missing $LOGO" >&2; exit 1; }
[[ -f "$FONT" ]] || FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
mkdir -p "$OUT_DIR"

if [[ "$FORCE" -eq 0 && -f "$OUT" ]]; then
  needs_rebuild=0
  for stamp in "$LOGO" "${BASH_SOURCE[0]}"; do
    [[ "$stamp" -nt "$OUT" ]] && needs_rebuild=1 && break
  done
  if [[ "$needs_rebuild" -eq 0 && -f "$SYSTEM_ENV" && "$SYSTEM_ENV" -nt "$OUT" ]]; then
    needs_rebuild=1
  fi
  [[ "$needs_rebuild" -eq 0 ]] && exit 0
fi

case "$ROTATION" in
  90) ROTATE_FILTER=";[base]rotate=angle=PI/2:fillcolor=black@1:ow=${CANVAS_W}:oh=${CANVAS_H}[out]" ;;
  -90) ROTATE_FILTER=";[base]rotate=angle=-PI/2:fillcolor=black@1:ow=${CANVAS_W}:oh=${CANVAS_H}[out]" ;;
  *) ROTATE_FILTER=";[base]copy[out]" ;;
esac

tmp="$(mktemp "${TMPDIR:-/tmp}/sportassist-idle.XXXXXX.png")"
trap 'rm -f "$tmp"' EXIT

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=black:s=${CANVAS_W}x${CANVAS_H}:d=1" \
  -i "$LOGO" \
  -filter_complex "
    [1:v]scale=-1:${LOGO_MAX_H}:force_original_aspect_ratio=decrease[logo];
    [0:v][logo]overlay=x=(W-w)/2:y=(H-h)/2-80[composed];
    [composed]drawtext=fontfile=${FONT}:text='Sport Assist':fontsize=108:fontcolor=white:borderw=2:bordercolor=black@0.6:x=(w-text_w)/2:y=h/2+520[base]${ROTATE_FILTER}
  " \
  -map "[out]" -frames:v 1 -f image2 "$tmp"

mv -f "$tmp" "$OUT"
trap - EXIT
