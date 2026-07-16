#!/usr/bin/env bash
set -euo pipefail
exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/onvif_osd.py "$@"
