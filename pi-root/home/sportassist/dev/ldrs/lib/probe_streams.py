#!/usr/bin/env python3
"""Read-only ONVIF stream/capability probe — JSON to stdout."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.env_util import SPORTASSIST_ETC, load_env
from lib.ffprobe_util import build_rtsp_url, probe_rtsp
from lib.onvif_client import connect, get_profiles, onvif_available, profile_info


def eligible_stream(info: Dict[str, Any]) -> bool:
    if info.get("codec") == "mjpeg":
        return False
    return int(info.get("fps") or 0) >= 25


def main() -> int:
    if len(sys.argv) >= 5:
        ip, username, password = sys.argv[1], sys.argv[2], sys.argv[3]
        port = int(sys.argv[4])
    else:
        env = load_env(SPORTASSIST_ETC / "camera.env")
        ip = env.get("CAMERA_IP", "")
        username = env.get("CAMERA_USERNAME", "")
        password = env.get("CAMERA_PASSWORD", "")
        port = int(env.get("CAMERA_RTSP_PORT", "554"))

    if not ip or not username:
        print(json.dumps({"streams": [], "error": "missing_credentials"}))
        return 1

    if not onvif_available():
        print(json.dumps({"streams": [], "error": "onvif_not_installed"}))
        return 1

    try:
        cam = connect(ip, port, username, password)
        profiles = get_profiles(cam)
        streams: List[Dict[str, Any]] = []
        codecs_seen: set[str] = set()
        for p in profiles:
            info = profile_info(cam, p)
            if info.get("codec"):
                codecs_seen.add(info["codec"])
            if eligible_stream(info):
                streams.append(info)
        supported = [
            {"id": "h264", "label": "H.264", "eligible": True},
            {"id": "h265", "label": "H.265", "eligible": "h265" in codecs_seen},
            {"id": "ultra265", "label": "Ultra 265", "eligible": "h265" in codecs_seen},
            {
                "id": "mjpeg",
                "label": "MJPEG",
                "eligible": False,
            },
        ]
        print(
            json.dumps(
                {
                    "streams": streams,
                    "capabilities": {"supportedCodecs": supported},
                    "error": None,
                }
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"streams": [], "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
