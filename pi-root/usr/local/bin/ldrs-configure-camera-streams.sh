#!/usr/bin/env bash
set -euo pipefail
if [[ -t 0 ]]; then
  exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/configure_streams.py "$@"
else
  exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/configure_streams.py
fi
