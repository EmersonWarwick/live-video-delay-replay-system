#!/usr/bin/env bash
# Discover cameras — JSON list on stdout (exit 0 even when none found).
set -euo pipefail

LDRS_ROOT="/home/sportassist/dev/ldrs"
export PYTHONPATH="$LDRS_ROOT${PYTHONPATH:+:$PYTHONPATH}"
shopt -s nullglob
for site in /home/sportassist/.local/lib/python3.*/site-packages; do
  [[ -d "$site" ]] && export PYTHONPATH="$site${PYTHONPATH:+:$PYTHONPATH}"
done

if [[ -x /usr/local/bin/ldrs-python3.sh ]]; then
  exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/discover_cameras.py "$@"
fi

exec /usr/bin/python3 /home/sportassist/dev/ldrs/lib/discover_cameras.py "$@"
