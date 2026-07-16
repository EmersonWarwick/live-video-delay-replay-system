#!/usr/bin/env python3
"""Assign camera: factory login → sportassist user + SportAssistCam hostname."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.camera_assign import (
    ASSIGNED_HOSTNAME,
    ASSIGNED_USERNAME,
    generate_assigned_password,
    provision_assigned_user,
    set_camera_hostname_onvif,
)
from lib.env_util import SPORTASSIST_ETC, update_env_keys
from lib.onvif_client import (
    connect_onvif,
    device_id_from_information,
    get_device_information,
    onvif_available,
    prepare_live_streaming,
    reported_name_from_information,
)
from lib.onvif_lens import apply_active_preset

CONFIGURE = Path(__file__).resolve().parent / "configure_streams.py"


def main() -> int:
    data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    ip = (data.get("ip") or "").strip()
    current_user = (data.get("currentUsername") or data.get("username") or "").strip()
    current_pass = data.get("currentPassword") or data.get("password") or ""
    onvif_port = int(data.get("onvifPort") or 80)
    rtsp_port = int(data.get("rtspPort") or 554)

    if not ip or not current_user or not current_pass:
        print(json.dumps({"ok": False, "error": "missing_fields"}))
        return 1
    if not onvif_available():
        print(json.dumps({"ok": False, "error": "onvif_not_installed"}))
        return 1

    new_password = generate_assigned_password()

    try:
        cam = connect_onvif(ip, current_user, current_pass, port=onvif_port)
        device_info = get_device_information(cam)
        device_id = device_id_from_information(device_info)
        reported_name = reported_name_from_information(device_info)
        if not device_id:
            device_id = reported_name or f"onvif-{ip.replace('.', '-')}"

        provision_assigned_user(cam, ASSIGNED_USERNAME, new_password)
        set_camera_hostname_onvif(cam, ASSIGNED_HOSTNAME)
        prepare_live_streaming(cam)
        cam = connect_onvif(ip, ASSIGNED_USERNAME, new_password, port=onvif_port)

        env_updates = {
            "CAMERA_HOSTNAME": ASSIGNED_HOSTNAME,
            "CAMERA_IP": ip,
            "CAMERA_USERNAME": ASSIGNED_USERNAME,
            "CAMERA_PASSWORD": new_password,
            "CAMERA_RTSP_PORT": str(rtsp_port),
            "CAMERA_ONVIF_PORT": str(onvif_port),
            "CAMERA_ASSIGNED": "1",
            "CAMERA_DEVICE_ID": device_id,
            "CAMERA_REPORTED_NAME": reported_name,
        }
        update_env_keys(SPORTASSIST_ETC / "camera.env", env_updates)

        payload = json.dumps(
            {
                "ip": ip,
                "username": ASSIGNED_USERNAME,
                "password": new_password,
                "rtspPort": rtsp_port,
                "onvifPort": onvif_port,
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
        if result.get("configured"):
            try:
                cam_live = connect_onvif(ip, ASSIGNED_USERNAME, new_password, port=onvif_port)
                prepare_live_streaming(cam_live)
            except Exception:
                pass
            try:
                apply_active_preset(force=True)
            except Exception:
                pass
        out = {
            "ok": result.get("configured", True),
            "assigned": True,
            "hostname": ASSIGNED_HOSTNAME,
            "deviceId": device_id,
            "reportedName": reported_name,
            "username": ASSIGNED_USERNAME,
            "password": new_password,
            "cameraConnected": result.get("configured", True),
            **result,
        }
        print(json.dumps(out))
        return 0
    except Exception as exc:
        msg = str(exc).lower()
        if "authorized" in msg or "authentication" in msg or ("auth" in msg and "fail" in msg):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "authentication_failed",
                        "hint": "Use the camera admin credentials set privately in the vendor Web UI before Assign.",
                    }
                )
            )
        elif "unreachable" in msg or "timeout" in msg:
            print(json.dumps({"ok": False, "error": "onvif_unreachable"}))
        else:
            print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
