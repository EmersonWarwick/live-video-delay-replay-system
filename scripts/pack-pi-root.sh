#!/usr/bin/env bash
# Build pi-root-sync.tar.gz on the build PC (Mac/Linux). Run from repo root or scripts/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT="${1:-pi-root-sync.tar.gz}"

# Mac does not preserve +x in git; ensure scripts are executable in the tarball.
chmod +x pi-root/usr/local/bin/ldrs-*.sh 2>/dev/null || true

# Mac: omit Apple metadata; Pi extract uses --no-same-owner (see build-instructions.md §8).
# Never pack per-device secrets — Pi keeps /etc/sportassist/{camera,network}.env across updates.
COPYFILE_DISABLE=1 tar czf "$OUT" -C pi-root \
  --exclude='./etc/sportassist/camera.env' \
  --exclude='./etc/sportassist/network.env' \
  --exclude='./etc/sportassist/wifi-network.env' \
  .

echo "Created $ROOT/$OUT ($(du -h "$OUT" | awk '{print $1}'))"
