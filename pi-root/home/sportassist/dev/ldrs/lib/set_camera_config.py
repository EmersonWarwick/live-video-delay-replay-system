#!/usr/bin/env python3
"""Save camera credentials and run ONVIF stream configure."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.camera_names import canonical_hostname, is_acceptable_camera_hostname
from lib.env_util import SPORTASSIST_ETC, update_env_keys

CONFIGURE = Path(__file__).resolve().parent / "configure_streams.py"


def main() -> int:
    if len(sys.argv) < 5:
        print("usage: set_camera_config.py hostname ip username password [port]", file=sys.stderr)
        return 2
    hostname = canonical_hostname(sys.argv[1])
    ip = sys.argv[2]
    username = sys.argv[3]
    password = sys.argv[4]
    port = sys.argv[5] if len(sys.argv) > 5 else "554"
    onvif_port = sys.argv[6] if len(sys.argv) > 6 else "80"

    if not is_acceptable_camera_hostname(hostname):
        print(json.dumps({"ok": False, "error": "invalid_hostname"}))
        return 1
    if not username or len(password) > 128:
        print(json.dumps({"ok": False, "error": "invalid_credentials"}))
        return 1

    update_env_keys(
        SPORTASSIST_ETC / "camera.env",
        {
            "CAMERA_HOSTNAME": hostname,
            "CAMERA_IP": ip,
            "CAMERA_USERNAME": username,
            "CAMERA_PASSWORD": password,
            "CAMERA_RTSP_PORT": port,
            "CAMERA_ONVIF_PORT": onvif_port,
        },
    )

    payload = json.dumps(
        {
            "ip": ip,
            "username": username,
            "password": password,
            "rtspPort": int(port),
            "onvifPort": int(onvif_port),
        }
    )
    proc = subprocess.run(
        [sys.executable, str(CONFIGURE)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout or proc.stderr or '{"configured":false}')
        return proc.returncode
    result = json.loads(proc.stdout or "{}")
    result["ok"] = result.get("configured", True)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
