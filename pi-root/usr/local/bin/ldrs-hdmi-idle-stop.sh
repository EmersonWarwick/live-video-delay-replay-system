#!/usr/bin/env bash
# Stop HDMI idle logo so video playback can use the display.
set -euo pipefail

sudo systemctl stop ldrs-hdmi-idle.service
