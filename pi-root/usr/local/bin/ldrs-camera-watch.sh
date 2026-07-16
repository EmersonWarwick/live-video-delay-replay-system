#!/usr/bin/env bash
# Camera watchdog — rediscover camera and restart ingest when stream is lost.
set -euo pipefail

exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/resolve_camera.py --watch
