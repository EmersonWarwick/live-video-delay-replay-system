#!/usr/bin/env bash
# Delete all HLS segments and playlists — fresh delayed pipeline (spec-hls-replay-buffer.md).
set -euo pipefail

for dir in /var/lib/sportassist/hls /var/lib/sportassist/hls-4k; do
  mkdir -p "$dir"
  find "$dir" -maxdepth 1 -type f -delete 2>/dev/null || true
done
echo "HLS buffers cleared"
