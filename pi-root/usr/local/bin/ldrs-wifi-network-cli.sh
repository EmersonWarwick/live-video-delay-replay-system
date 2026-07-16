#!/usr/bin/env bash
# Wi-Fi network CLI wrapper — runs privileged Wi-Fi settings commands as root.
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

CMD="${1:-}"
shift || true

if [[ -z "$CMD" ]]; then
  echo "usage: ldrs-wifi-network-cli.sh <status|config|scan|save|set-hostname|apply|switch-ap|switch-client|forget|logs> [json]" >&2
  exit 2
fi

# Do not use ${1:-{}} — a JSON argument ending with "}" gets an extra "}" appended.
JSON="{}"
if [[ $# -gt 0 && -n "${1:-}" ]]; then
  JSON="$1"
fi
exec /usr/local/bin/ldrs-python3.sh /home/sportassist/dev/ldrs/lib/network_cli.py "$CMD" "$JSON"
