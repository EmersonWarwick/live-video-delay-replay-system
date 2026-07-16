#!/usr/bin/env python3
"""Verify assigned sportassist ONVIF login at boot (optional admin check)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.env_util import SPORTASSIST_ETC, load_env
from lib.onvif_client import connect_onvif, get_profiles, onvif_available

RUN_IP = Path("/run/sportassist/camera.ip")


def _camera_ip(env: Dict[str, str]) -> str:
    if RUN_IP.is_file():
        ip = RUN_IP.read_text(encoding="utf-8").strip()
        if ip:
            return ip
    return env.get("CAMERA_IP", "").strip()


def _test_login(ip: str, user: str, password: str, onvif_port: int) -> Dict[str, Any]:
    if not ip or not user or not password:
        return {"ok": False, "error": "missing_credentials"}
    if not onvif_available():
        return {"ok": False, "error": "onvif_not_installed"}
    try:
        cam = connect_onvif(ip, user, password, port=onvif_port)
        profiles = get_profiles(cam)
        return {"ok": True, "profileCount": len(profiles)}
    except Exception as exc:
        msg = str(exc).lower()
        if "authorized" in msg or "authentication" in msg or ("auth" in msg and "fail" in msg):
            return {"ok": False, "error": "authentication_failed"}
        if "unreachable" in msg or "timeout" in msg:
            return {"ok": False, "error": "onvif_unreachable"}
        return {"ok": False, "error": str(exc)}


def verify_credentials() -> Dict[str, Any]:
    env = load_env(SPORTASSIST_ETC / "camera.env")
    if env.get("CAMERA_ASSIGNED") != "1":
        return {"ok": True, "skipped": True, "reason": "not_assigned"}

    ip = _camera_ip(env)
    onvif_port = int(env.get("CAMERA_ONVIF_PORT") or 80)
    if not ip:
        return {"ok": False, "error": "no_camera_ip"}

    assigned_user = env.get("CAMERA_USERNAME", "").strip()
    assigned_pass = env.get("CAMERA_PASSWORD", "")
    assigned = _test_login(ip, assigned_user, assigned_pass, onvif_port)

    out: Dict[str, Any] = {
        "ok": bool(assigned.get("ok")),
        "ip": ip,
        "assigned": {
            "username": assigned_user,
            **assigned,
        },
    }

    # Optional: only if operator stored a private admin password on the Pi.
    # Never ship a shared default password in source.
    admin_user = (env.get("CAMERA_SUPERUSER_USERNAME") or "admin").strip()
    admin_pass = env.get("CAMERA_SUPERUSER_PASSWORD", "")
    if admin_pass:
        admin = _test_login(ip, admin_user, admin_pass, onvif_port)
        out["admin"] = admin
        if not admin.get("ok"):
            out["warning"] = (
                "Stored CAMERA_SUPERUSER_* login failed — "
                "admin password may have changed on the camera web UI."
            )

    if not assigned.get("ok"):
        out["error"] = "assigned_user_auth_failed"
        out["hint"] = "Re-assign camera in Settings or restore sportassist user on the camera."
    return out


def main() -> int:
    result = verify_credentials()
    print(json.dumps(result))
    if result.get("skipped"):
        return 0
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
