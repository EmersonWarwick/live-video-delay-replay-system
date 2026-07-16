"""Build /api/status JSON from buffer state."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from lib.buffer_util import hdmi_focus_mode
from lib.delay_playlist_util import delayed_playlist_status
from lib.delay_util import (
    delay_bounds,
    live_delay_seconds,
    pipeline_latency_seconds,
    playback_offset_seconds,
)
from lib.env_util import load_env

HLS_WIFI = Path("/var/lib/sportassist/hls")
HLS_4K = Path("/var/lib/sportassist/hls-4k")
SYSTEM_ENV = Path("/etc/sportassist/system.env")
CAMERA_ENV = Path("/etc/sportassist/camera.env")
RUN_IP = Path("/run/sportassist/camera.ip")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def replay_buffer_active() -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", "ldrs-replay-buffer.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() == "active"
    except Exception:
        return False


def hdmi_live_service_active() -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", "ldrs-hdmi-live.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() == "active"
    except Exception:
        return False


def hdmi_active_service() -> str:
    """Which HDMI systemd unit is running: live, delayed, or off."""
    for unit, label in (
        ("ldrs-hdmi-live.service", "live"),
        ("ldrs-hdmi-delay.service", "delayed"),
    ):
        try:
            out = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.stdout.strip() == "active":
                return label
        except Exception:
            continue
    return "off"


def camera_configured() -> bool:
    env = load_env(CAMERA_ENV)
    return bool(
        env.get("CAMERA_RTSP_PATH")
        and env.get("CAMERA_IP")
        and env.get("CAMERA_USERNAME")
        and env.get("CAMERA_PASSWORD")
    )


def camera_connected() -> bool:
    env = load_env(CAMERA_ENV)
    if not env.get("CAMERA_RTSP_PATH") or not env.get("CAMERA_IP"):
        return False
    if hdmi_focus_mode():
        return hdmi_live_service_active()
    if not replay_buffer_active():
        return False
    wifi = HLS_WIFI / "live.m3u8"
    hdmi = HLS_4K / "live.m3u8"
    return wifi.is_file() or hdmi.is_file()


def segment_times(playlist: Path, offset_behind_edge_s: int) -> Dict[str, Optional[str]]:
    if not playlist.is_file():
        return {
            "oldestSegmentTime": None,
            "latestSegmentTime": None,
            "safeDelayEdgeTime": None,
        }
    mtime = datetime.fromtimestamp(playlist.stat().st_mtime, tz=timezone.utc)
    sys_env = load_env(SYSTEM_ENV)
    buffer_s = int(sys_env.get("BUFFER_DURATION_SECONDS", "1200"))
    oldest = mtime - timedelta(seconds=buffer_s)
    safe = mtime - timedelta(seconds=offset_behind_edge_s)
    return {
        "oldestSegmentTime": _iso(oldest),
        "latestSegmentTime": _iso(mtime),
        "safeDelayEdgeTime": _iso(safe),
    }


def buffer_health() -> str:
    if hdmi_focus_mode():
        return "focus"
    wifi = HLS_WIFI / "live.m3u8"
    if not wifi.is_file():
        return "warming" if replay_buffer_active() else "error"
    if replay_buffer_active() and not hdmi_focus_mode():
        if not delayed_playlist_status().get("delayedSyncReady"):
            return "warming"
    segs = list(HLS_WIFI.glob("*.m4s")) + list(HLS_WIFI.glob("*.ts"))
    if len(segs) < 5:
        return "warming"
    return "ok"


def build_status() -> Dict[str, Any]:
    sys_env = load_env(SYSTEM_ENV)
    cam_env = load_env(CAMERA_ENV)
    delay = live_delay_seconds(sys_env)
    pipeline = pipeline_latency_seconds(sys_env)
    offset = playback_offset_seconds(sys_env)
    delay_min, delay_max = delay_bounds(sys_env)
    buffer_s = int(sys_env.get("BUFFER_DURATION_SECONDS", "1200"))
    seg_dur = float(sys_env.get("HLS_SEGMENT_DURATION", "1"))
    times = segment_times(HLS_WIFI / "live.m3u8", offset)
    health = buffer_health()
    wifi_bytes = sum(f.stat().st_size for f in HLS_WIFI.glob("*") if f.is_file())
    hdmi_bytes = sum(f.stat().st_size for f in HLS_4K.glob("*") if f.is_file())
    hdmi_mode = sys_env.get("HDMI_OUTPUT_MODE", "delayed")
    if hdmi_mode not in ("delayed", "live"):
        hdmi_mode = "delayed"

    delay_state = delayed_playlist_status()
    replay_delayed = (
        not hdmi_focus_mode()
        and delay_state["delayedSyncReady"]
    )

    return {
        "cameraConnected": camera_connected(),
        "cameraConfigured": camera_configured(),
        "bufferHealth": health,
        "bufferWarming": health in ("warming",),
        "liveDelaySeconds": delay,
        "pipelineLatencySeconds": pipeline,
        "playbackOffsetSeconds": offset,
        "livePlaylist": "/hls/live.m3u8",
        "reviewPlaylist": "/hls/buffer.m3u8",
        "replayPlaylist": "/hls/live.m3u8",
        "scrubPlaylist": "/hls/buffer.m3u8",
        "hdmiSyncPlaylist": "/hls/sync.m3u8",
        "replayUsingDelayedPlaylist": replay_delayed,
        **delay_state,
        "liveDelayMinSeconds": delay_min,
        "liveDelayMaxSeconds": delay_max,
        "hdmiEnabled": sys_env.get("HDMI_ENABLED", "1") == "1",
        "hdmiOutputMode": hdmi_mode,
        "hdmiFocusMode": hdmi_mode == "live" and sys_env.get("HDMI_ENABLED", "1") == "1",
        "hdmiActiveService": hdmi_active_service(),
        "replayBufferActive": replay_buffer_active(),
        "bufferDurationSeconds": buffer_s,
        "segmentDurationSeconds": seg_dur,
        "activeClients": 0,
        "ingestFallbackStep": int(cam_env.get("INGEST_FALLBACK_STEP") or 0) or None,
        "ingestGop": int(cam_env.get("INGEST_GOP") or 25),
        "hdmiBuffer": {
            "width": int(cam_env.get("INGEST_WIDTH") or 0),
            "height": int(cam_env.get("INGEST_HEIGHT") or 0),
            "diskBytes": hdmi_bytes,
        },
        "wifiBuffer": {
            "width": int(cam_env.get("INGEST_SUB_WIDTH") or 1920),
            "height": int(cam_env.get("INGEST_SUB_HEIGHT") or 1080),
            "diskBytes": wifi_bytes,
        },
        **times,
    }
