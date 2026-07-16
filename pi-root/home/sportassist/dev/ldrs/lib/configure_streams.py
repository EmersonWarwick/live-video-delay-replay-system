#!/usr/bin/env python3
"""ONVIF configure camera streams — fallback ladder; writes camera.env."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.buffer_util import restart_replay_pipeline
from lib.onvif_lens import apply_active_preset
from lib.env_util import SPORTASSIST_ETC, load_env, update_env_keys
from lib.ffprobe_util import build_rtsp_url, probe_ok, probe_rtsp
from lib.onvif_client import (
    connect_onvif,
    get_profiles,
    onvif_available,
    prepare_live_streaming,
    profile_info,
    set_encoder,
)

# (step, width, height, fps, codec_try_order)
LADDER: List[Tuple[int, int, int, int, List[str]]] = [
    (1, 3840, 2160, 25, ["ultra265", "h265", "h264"]),
    (2, 2560, 1440, 25, ["ultra265", "h265", "h264"]),
    (3, 1920, 1080, 25, ["h264", "h265", "ultra265"]),
]

BITRATE = {3840: 12_000_000, 2560: 8_000_000, 1920: 5_000_000}
SUB_BITRATE = 5_000_000
PROBE_TIMEOUT_S = 5


def pick_main_profile(profiles: list) -> Any:
    best = profiles[0]
    best_pixels = 0
    for p in profiles:
        try:
            v = p.VideoEncoderConfiguration.Resolution
            px = int(v.Width) * int(v.Height)
            if px > best_pixels:
                best_pixels = px
                best = p
        except Exception:
            continue
    return best


def pick_sub_profile(profiles: list, main_profile: Any) -> Optional[Any]:
    for p in profiles:
        if p.token == main_profile.token:
            continue
        try:
            v = p.VideoEncoderConfiguration.Resolution
            if int(v.Width) <= 1920 and int(v.Height) <= 1080:
                return p
        except Exception:
            continue
    return profiles[1] if len(profiles) > 1 else None


def configure_sub(cam, sub_profile, ip, port, user, password) -> Optional[Dict[str, Any]]:
    if not sub_profile:
        return None
    try:
        set_encoder(cam, sub_profile, 1920, 1080, 25, "h264", SUB_BITRATE, 25)
        info = profile_info(cam, sub_profile)
        url = build_rtsp_url(ip, port, info["rtspPath"], user, password)
        if not probe_ok(url, min_fps=25, timeout_s=PROBE_TIMEOUT_S):
            return None
        return {
            "rtspPath": info["rtspPath"],
            "width": 1920,
            "height": 1080,
            "fps": 25,
            "codec": "h264",
            "gop": 25,
            "bitrate": SUB_BITRATE,
            "label": info.get("label", "Sub stream"),
        }
    except Exception:
        return None


def main() -> int:
    data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    env = load_env(SPORTASSIST_ETC / "camera.env")
    ip = data.get("ip") or env.get("CAMERA_IP") or (sys.argv[1] if len(sys.argv) > 1 else "")
    user = data.get("username") or env.get("CAMERA_USERNAME", "")
    password = data.get("password") or env.get("CAMERA_PASSWORD", "")
    port = int(data.get("rtspPort") or env.get("CAMERA_RTSP_PORT", "554"))
    onvif_port = int(data.get("onvifPort") or env.get("CAMERA_ONVIF_PORT") or 80)

    if not ip or not user or not password:
        print(json.dumps({"configured": False, "error": "missing_credentials"}))
        return 1
    if not onvif_available():
        print(json.dumps({"configured": False, "error": "onvif_not_installed"}))
        return 1

    try:
        cam = connect_onvif(ip, user, password, port=onvif_port)
        profiles = get_profiles(cam)
        if not profiles:
            raise RuntimeError("no_onvif_profiles")
        main_profile = pick_main_profile(profiles)

        result: Optional[Dict[str, Any]] = None
        fallback_step = 0
        for step, w, h, fps, codecs in LADDER:
            for codec in codecs:
                try:
                    br = BITRATE.get(w, 5_000_000)
                    set_encoder(cam, main_profile, w, h, fps, codec, br, 25)
                    info = profile_info(cam, main_profile)
                    url = build_rtsp_url(ip, port, info["rtspPath"], user, password)
                    pr = probe_rtsp(url, timeout_s=PROBE_TIMEOUT_S)
                    if pr.get("ok") and int(pr.get("fps") or 0) >= 25:
                        store_codec = "ultra265" if codec == "ultra265" else pr.get("codec", codec)
                        result = {
                            "width": w,
                            "height": h,
                            "fps": fps,
                            "codec": store_codec,
                            "gop": 25,
                            "bitrate": br,
                            "rtspPath": info["rtspPath"],
                            "label": info.get("label", "Main stream"),
                        }
                        fallback_step = step
                        break
                except Exception:
                    continue
            if result:
                break

        if not result:
            print(json.dumps({"configured": False, "error": "no_valid_profile"}))
            return 1

        prepare_live_streaming(cam)

        sub = None
        if result["width"] > 1920 or result["height"] > 1080:
            sub_prof = pick_sub_profile(profiles, main_profile)
            sub = configure_sub(cam, sub_prof, ip, port, user, password)

        updates = {
            "CAMERA_IP": ip,
            "CAMERA_USERNAME": user,
            "CAMERA_PASSWORD": password,
            "CAMERA_RTSP_PORT": str(port),
            "CAMERA_ONVIF_PORT": str(onvif_port),
            "CAMERA_RTSP_TRANSPORT": "tcp",
            "CAMERA_RTSP_PATH": result["rtspPath"],
            "INGEST_WIDTH": str(result["width"]),
            "INGEST_HEIGHT": str(result["height"]),
            "INGEST_FPS": str(result["fps"]),
            "INGEST_CODEC": result["codec"],
            "INGEST_BITRATE": str(result["bitrate"]),
            "INGEST_GOP": str(result["gop"]),
            "CAMERA_STREAM_LABEL": result["label"],
            "INGEST_FALLBACK_STEP": str(fallback_step),
        }
        if sub:
            updates.update(
                {
                    "CAMERA_RTSP_PATH_SUB": sub["rtspPath"],
                    "INGEST_SUB_WIDTH": str(sub["width"]),
                    "INGEST_SUB_HEIGHT": str(sub["height"]),
                    "INGEST_SUB_FPS": str(sub["fps"]),
                    "INGEST_SUB_CODEC": sub["codec"],
                    "INGEST_SUB_BITRATE": str(sub["bitrate"]),
                    "INGEST_SUB_GOP": str(sub["gop"]),
                }
            )
        update_env_keys(SPORTASSIST_ETC / "camera.env", updates)

        out = {
            "configured": True,
            "fallbackStep": fallback_step,
            "main": result,
            "sub": sub,
            "error": None,
        }
        print(json.dumps(out))
        restart_replay_pipeline()
        try:
            apply_active_preset(force=True)
        except Exception:
            pass
        return 0
    except Exception as exc:
        msg = str(exc).lower()
        if "authorized" in msg or "authentication" in msg or ("auth" in msg and "fail" in msg):
            print(
                json.dumps(
                    {
                        "configured": False,
                        "error": "authentication_failed",
                        "hint": "Use the camera admin credentials set privately in the vendor Web UI before Assign.",
                    }
                )
            )
        elif "unreachable" in msg or "timed out" in msg or "timeout" in msg:
            print(json.dumps({"configured": False, "error": "onvif_unreachable"}))
        else:
            print(json.dumps({"configured": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
