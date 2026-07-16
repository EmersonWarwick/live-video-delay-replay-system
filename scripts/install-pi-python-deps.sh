#!/usr/bin/env bash
# Install ONVIF pip packages on Raspberry Pi OS (avoids isodate 0.0.0 apt stub conflict).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQ="${ROOT}/requirements-pip.txt"

if [[ ! -f "$REQ" ]]; then
  echo "Missing $REQ" >&2
  exit 1
fi

sudo apt install -y python3-zeep python3-flask

# Pi OS ships a dummy isodate 0.0.0 deb; pip must ignore it when pulling dependencies.
sudo pip3 install \
  --break-system-packages \
  --ignore-installed isodate \
  --no-binary onvif-zeep \
  -r "$REQ"

sudo bash "${ROOT}/scripts/install-onvif-wsdl.sh"

sudo python3 -c "
import sys
sys.path.insert(0, '/home/sportassist/dev/ldrs')
from lib.onvif_client import onvif_wsdl_dir, onvif_available
print('onvif:', onvif_available(), 'wsdl:', onvif_wsdl_dir())
"
if [[ -x /usr/local/bin/ldrs-python3.sh ]]; then
  sudo /usr/local/bin/ldrs-python3.sh -c "
import sys
sys.path.insert(0, '/home/sportassist/dev/ldrs')
from lib.onvif_client import onvif_wsdl_dir
print('ldrs-python3 wsdl:', onvif_wsdl_dir())
"
fi
