#!/usr/bin/env python3
"""Quick ONVIF login test — does not configure streams."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.env_util import SPORTASSIST_ETC, load_env
from lib.onvif_client import connect_onvif, get_profiles, onvif_available


def main() -> int:
    if sys.stdin.isatty():
        if len(sys.argv) < 4:
            print(
                "usage: test_onvif_auth.py ip username password [onvif_port]",
                file=sys.stderr,
            )
            return 2
        ip, user, password = sys.argv[1], sys.argv[2], sys.argv[3]
        onvif_port = int(sys.argv[4]) if len(sys.argv) > 4 else 80
    else:
        data = json.load(sys.stdin)
        ip = data.get("ip", "")
        user = data.get("username", "")
        password = data.get("password", "")
        onvif_port = int(data.get("onvifPort") or 80)

    if not ip or not user or not password:
        print(json.dumps({"ok": False, "error": "missing_credentials"}))
        return 1
    if not onvif_available():
        print(json.dumps({"ok": False, "error": "onvif_not_installed"}))
        return 1

    try:
        cam = connect_onvif(ip, user, password, port=onvif_port)
        profiles = get_profiles(cam)
        print(
            json.dumps(
                {
                    "ok": True,
                    "profileCount": len(profiles),
                    "onvifPort": onvif_port,
                }
            )
        )
        return 0
    except Exception as exc:
        msg = str(exc).lower()
        if "authorized" in msg or "authentication" in msg or ("auth" in msg and "fail" in msg):
            err = "authentication_failed"
        elif "unreachable" in msg or "timeout" in msg:
            err = "onvif_unreachable"
        else:
            err = str(exc)
        print(json.dumps({"ok": False, "error": err}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
