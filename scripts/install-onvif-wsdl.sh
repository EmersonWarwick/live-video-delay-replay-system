#!/usr/bin/env bash
# Place onvif-zeep WSDL files where ONVIFCamera expects them (site-packages/wsdl).
# onvif-zeep uses setup.py data_files with a build-time Python version in the path;
# pip wheels often leave devicemgmt.wsdl under lib/pythonX.Y/... for the wrong Y.
set -euo pipefail

PYVER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
DEST="/usr/local/lib/python${PYVER}/site-packages/wsdl"
DIST="/usr/local/lib/python${PYVER}/dist-packages/wsdl"

if [[ -f "${DEST}/devicemgmt.wsdl" ]]; then
  :
elif wsrc="$(find /usr/local/lib -name devicemgmt.wsdl 2>/dev/null | head -1)" && [[ -n "$wsrc" ]]; then
  echo "Copying WSDL from $(dirname "$wsrc") -> ${DEST}"
  mkdir -p "$DEST"
  cp -a "$(dirname "$wsrc")/." "$DEST/"
else
  echo "Extracting WSDL from onvif-zeep sdist..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  pip3 download --no-deps --no-binary onvif-zeep 'onvif-zeep>=0.2.12' -d "$tmp"
  tar -xzf "$tmp"/onvif_zeep-*.tar.gz -C "$tmp"
  mkdir -p "$DEST"
  cp -a "$tmp"/onvif_zeep-*/wsdl/. "$DEST/"
fi

if [[ -f "${DEST}/devicemgmt.wsdl" && ! -e "${DIST}/devicemgmt.wsdl" ]]; then
  mkdir -p "$(dirname "$DIST")"
  ln -sfn "$DEST" "$DIST"
  echo "Symlinked ${DIST} -> ${DEST}"
fi

if [[ ! -f "${DEST}/devicemgmt.wsdl" ]]; then
  echo "ERROR: devicemgmt.wsdl still missing at ${DEST}" >&2
  exit 1
fi
echo "WSDL OK: ${DEST}"
