"""Review timeline API — HLS scrub bounds for coach review (no full-file download)."""
from __future__ import annotations

from typing import Any, Dict

from lib.status_util import build_status

LIVE_PLAYLIST = "/hls/live.m3u8"
REVIEW_PLAYLIST = "/hls/buffer.m3u8"


def build_review() -> Dict[str, Any]:
    """Timeline + playlist URLs for native Review tab and browser /replay."""
    status = build_status()
    return {
        "ok": True,
        "cameraConnected": status.get("cameraConnected", False),
        "bufferHealth": status.get("bufferHealth", "error"),
        "bufferWarming": status.get("bufferWarming", True),
        "bufferDurationSeconds": status.get("bufferDurationSeconds", 1200),
        "segmentDurationSeconds": status.get("segmentDurationSeconds", 1.0),
        "liveDelaySeconds": status.get("liveDelaySeconds", 14),
        "playbackOffsetSeconds": status.get("playbackOffsetSeconds", 11),
        "oldestTime": status.get("oldestSegmentTime"),
        "latestTime": status.get("latestSegmentTime"),
        "liveEdgeTime": status.get("safeDelayEdgeTime"),
        "livePlaylist": LIVE_PLAYLIST,
        "reviewPlaylist": REVIEW_PLAYLIST,
        "wifiBuffer": status.get("wifiBuffer"),
        "delayedSyncReady": status.get("delayedSyncReady", False),
    }
