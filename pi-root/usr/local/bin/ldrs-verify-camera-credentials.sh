#!/usr/bin/env bash
# Log ONVIF auth health for admin + assigned sportassist user.
set -euo pipefail
exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/verify_camera_credentials.py
