#!/usr/bin/env bash
# Build RTSP URL with URL-encoded credentials (safe for shell and players).
set -euo pipefail
exec /usr/local/bin/ldrs-python3.sh - "$@" <<'PY'
from __future__ import annotations

import sys
from urllib.parse import quote

from lib.ffprobe_util import build_rtsp_url

if len(sys.argv) != 6:
    print("usage: ldrs-rtsp-url.sh IP PORT PATH USER PASS", file=sys.stderr)
    sys.exit(2)

ip, port_s, path, user, password = sys.argv[1:6]
port = int(port_s)
# encode userinfo for RTSP URI
user_q = quote(user, safe="")
pass_q = quote(password, safe="")
print(build_rtsp_url(ip, port, path, user_q, pass_q))
PY
