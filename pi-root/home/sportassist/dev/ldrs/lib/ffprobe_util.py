"""ffprobe validation for RTSP streams."""
from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, Optional


def build_rtsp_url(
    ip: str, port: int, path: str, username: str, password: str
) -> str:
    p = path if path.startswith("/") else f"/{path}"
    return f"rtsp://{username}:{password}@{ip}:{port}{p}"


def probe_rtsp(url: str, timeout_s: int = 10) -> Dict[str, Any]:
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-rtsp_transport",
        "tcp",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-i",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False
        )
        if proc.returncode != 0:
            return {"ok": False, "error": "ffprobe_failed"}
        data = json.loads(proc.stdout or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        return {"ok": False, "error": "no_video"}
    fps = 25.0
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "25/1"
    if "/" in str(rate):
        num, den = str(rate).split("/", 1)
        try:
            fps = float(num) / float(den) if float(den) else 25.0
        except ValueError:
            fps = 25.0
    codec = video.get("codec_name", "h264")
    return {
        "ok": True,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": round(fps),
        "codec": "h265" if codec in ("hevc", "h265") else codec,
    }


def probe_ok(url: str, min_fps: int = 25, timeout_s: int = 10) -> bool:
    r = probe_rtsp(url, timeout_s=timeout_s)
    return bool(r.get("ok")) and int(r.get("fps") or 0) >= min_fps
