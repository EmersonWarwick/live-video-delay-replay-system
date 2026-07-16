#!/usr/bin/env bash
# Run Pi helper Python with project + pip user site-packages (sudo drops sportassist ~/.local).
set -euo pipefail

LDRS_ROOT="/home/sportassist/dev/ldrs"
export PYTHONPATH="$LDRS_ROOT${PYTHONPATH:+:$PYTHONPATH}"

shopt -s nullglob
for site in /home/sportassist/.local/lib/python3.*/site-packages; do
  [[ -d "$site" ]] && export PYTHONPATH="$site${PYTHONPATH:+:$PYTHONPATH}"
done

exec /usr/bin/python3 "$@"
