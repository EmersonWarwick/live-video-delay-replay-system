"""Delayed HLS playlist health — Wi-Fi sync playlists."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from lib.hdmi_delay_util import hdmi_delay_status, hdmi_hls_playlist_ready

HLS_WIFI = Path("/var/lib/sportassist/hls")
DELAYED_WIFI = HLS_WIFI / "delayed_sync.m3u8"
HLS_4K = Path("/var/lib/sportassist/hls-4k")
DELAYED_HDMI = HLS_4K / "delayed_hdmi.m3u8"
DEFAULT_MAX_AGE_S = 3.0


def playlist_age_seconds(path: Path) -> Optional[float]:
    if not path.is_file():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def playlist_fresh(path: Path, max_age_s: float = DEFAULT_MAX_AGE_S) -> bool:
    age = playlist_age_seconds(path)
    return age is not None and age <= max_age_s


def hls_delay_updater_active() -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", "ldrs-hls-delay-playlists.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() == "active"
    except Exception as exc:
        print(
            f"delay_playlist_util: systemctl is-active failed: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return False


def delayed_playlist_status() -> dict:
    sync_age = playlist_age_seconds(DELAYED_WIFI)
    updater = hls_delay_updater_active()
    sync_fresh = sync_age is not None and sync_age <= DEFAULT_MAX_AGE_S
    hdmi_ready = hdmi_hls_playlist_ready()
    hdmi_age = playlist_age_seconds(DELAYED_HDMI)
    return {
        "delayedSyncReady": sync_fresh and updater,
        "delayedHdmiReady": hdmi_ready,
        "hlsDelayUpdaterActive": updater,
        "delayedSyncAgeSeconds": round(sync_age, 1) if sync_age is not None else None,
        "delayedHdmiAgeSeconds": round(hdmi_age, 1) if hdmi_age is not None else None,
        **hdmi_delay_status(),
    }
