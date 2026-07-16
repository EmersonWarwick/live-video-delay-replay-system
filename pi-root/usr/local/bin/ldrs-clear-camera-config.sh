#!/usr/bin/env bash
# Clear camera.env — used when toggling Ethernet mode or from Settings UI.
set -euo pipefail
exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/clear_camera_config.py
