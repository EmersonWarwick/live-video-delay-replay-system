"""HDMI delayed output — 4K HLS playlist readiness."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from lib.delay_util import hdmi_delay_seconds, hdmi_hls_offset_behind_edge_seconds, pipeline_latency_seconds
from lib.env_util import SPORTASSIST_ETC, load_env

HLS_4K = Path("/var/lib/sportassist/hls-4k")
LIVE_HDMI_PLAYLIST = HLS_4K / "live.m3u8"
DELAYED_HDMI_PLAYLIST = HLS_4K / "delayed_hdmi.m3u8"
SYSTEM_ENV = SPORTASSIST_ETC / "system.env"
PLAYLIST_MAX_AGE_S = 5.0


def hdmi_hls_playlist_ready(sys_env: Optional[Dict[str, str]] = None) -> bool:
    """True when the 4K ingest buffer has enough segments for the configured delay."""
    if not LIVE_HDMI_PLAYLIST.is_file():
        return False
    age = time.time() - LIVE_HDMI_PLAYLIST.stat().st_mtime
    if age > PLAYLIST_MAX_AGE_S:
        return False
    env = sys_env if sys_env is not None else load_env(SYSTEM_ENV)
    need = int(hdmi_hls_offset_behind_edge_seconds(env) + pipeline_latency_seconds(env)) + 3
    return len(list(HLS_4K.glob("*.m4s"))) >= need


def hdmi_delay_status(sys_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    env = sys_env if sys_env is not None else load_env(SYSTEM_ENV)
    return {
        "hdmiDelaySeconds": round(hdmi_delay_seconds(env), 1),
    }
