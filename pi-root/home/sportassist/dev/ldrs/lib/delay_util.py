"""Live delay math — total camera-to-display delay vs HLS-edge playback offset."""
from __future__ import annotations

from typing import Dict, Tuple

DEFAULT_PIPELINE_LATENCY_SECONDS = 3
DEFAULT_LIVE_DELAY_SECONDS = 14
DELAY_MAX_SECONDS = 60


def pipeline_latency_seconds(sys_env: Dict[str, str]) -> int:
    raw = sys_env.get("PIPELINE_LATENCY_SECONDS", str(DEFAULT_PIPELINE_LATENCY_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_PIPELINE_LATENCY_SECONDS
    return max(1, value)


def live_delay_seconds(sys_env: Dict[str, str]) -> int:
    raw = sys_env.get("LIVE_DELAY_SECONDS", str(DEFAULT_LIVE_DELAY_SECONDS))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIVE_DELAY_SECONDS


def delay_bounds(sys_env: Dict[str, str]) -> Tuple[int, int]:
    """Minimum is inherent pipeline latency — cannot delay less than the ingest edge."""
    pipeline = pipeline_latency_seconds(sys_env)
    return pipeline, DELAY_MAX_SECONDS


def hdmi_playback_bias_seconds(sys_env: Dict[str, str]) -> float:
    """Per-unit fine tune: positive = less HDMI delay (subtract from edge offset)."""
    raw = sys_env.get("HDMI_PLAYBACK_BIAS_SECONDS", "0")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def playback_offset_seconds(sys_env: Dict[str, str]) -> int:
    """Seconds behind the HLS live edge (Wi‑Fi tablet scrub edge)."""
    return int(round(playback_offset_behind_edge_seconds(sys_env)))


def hdmi_delay_seconds(sys_env: Dict[str, str]) -> float:
    """Wall-clock HDMI delay — total seconds from live to display."""
    return max(0.0, float(live_delay_seconds(sys_env)) - hdmi_playback_bias_seconds(sys_env))


def playback_offset_behind_edge_seconds(sys_env: Dict[str, str]) -> float:
    """Seconds behind the HLS live edge — uses playlist #EXTINF durations when trimming."""
    total = float(live_delay_seconds(sys_env))
    pipeline = float(pipeline_latency_seconds(sys_env))
    bias = hdmi_playback_bias_seconds(sys_env)
    return max(0.0, total - pipeline - bias)


def hdmi_hls_offset_behind_edge_seconds(sys_env: Dict[str, str]) -> float:
    """HLS edge offset so wall-clock HDMI delay matches LIVE_DELAY_SECONDS."""
    return playback_offset_behind_edge_seconds(sys_env)
