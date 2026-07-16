#!/usr/bin/env bash
# Verify camera IP or search network by device identifier — updates camera.env when relocated
set -euo pipefail
exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/resolve_camera.py
