"""Clear Pi HLS buffers and restart ingest — live edge after camera assign/configure."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Dict

from lib.delay_util import hdmi_delay_seconds
from lib.env_util import SPORTASSIST_ETC, load_env

HLS_WIFI = Path("/var/lib/sportassist/hls")
HLS_4K = Path("/var/lib/sportassist/hls-4k")
PLAYLIST_4K = HLS_4K / "live.m3u8"
PLAYLIST_WIFI = HLS_WIFI / "live.m3u8"
SYSTEM_ENV = SPORTASSIST_ETC / "system.env"


def _system_env() -> Dict[str, str]:
    return load_env(SYSTEM_ENV)


def _hdmi_mode() -> str:
    mode = _system_env().get("HDMI_OUTPUT_MODE", "delayed")
    return mode if mode in ("delayed", "live") else "delayed"


def _hdmi_enabled() -> bool:
    return _system_env().get("HDMI_ENABLED", "1") == "1"


def hdmi_focus_mode() -> bool:
    """Live to HDMI — lens focus only; no HLS ingest or buffer writes."""
    return _hdmi_enabled() and _hdmi_mode() == "live"


def _service_active(unit: str) -> bool:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() == "active"
    except Exception:
        return False


def ingest_playlist_stale(max_age_s: float = 20) -> bool:
    """True when Wi‑Fi HLS playlist is missing or not updating."""
    if not PLAYLIST_WIFI.is_file():
        return True
    try:
        return (time.time() - PLAYLIST_WIFI.stat().st_mtime) > max_age_s
    except OSError:
        return True


def ingest_needs_restart(max_age_s: float = 20) -> bool:
    if hdmi_focus_mode():
        return not _service_active("ldrs-hdmi-live.service")
    if not _service_active("ldrs-replay-buffer.service"):
        return True
    return ingest_playlist_stale(max_age_s=max_age_s)


def clear_hls_buffers() -> None:
    """Remove stale segments so clients never see pre-assign video."""
    for directory in (HLS_WIFI, HLS_4K):
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)


def _segment_count(directory: Path) -> int:
    return len(list(directory.glob("*.m4s")))


def stop_replay_buffer() -> None:
    subprocess.run(
        ["systemctl", "stop", "ldrs-hls-delay-playlists.service"],
        capture_output=True,
        timeout=20,
        check=False,
    )
    subprocess.run(
        ["systemctl", "stop", "ldrs-replay-buffer.service"],
        capture_output=True,
        timeout=45,
        check=False,
    )
    subprocess.run(
        ["systemctl", "disable", "ldrs-replay-buffer.service"],
        capture_output=True,
        timeout=20,
        check=False,
    )


def start_replay_buffer() -> None:
    subprocess.run(
        ["systemctl", "enable", "ldrs-replay-buffer.service"],
        capture_output=True,
        timeout=20,
        check=False,
    )
    subprocess.run(
        ["systemctl", "enable", "ldrs-hls-delay-playlists.service"],
        capture_output=True,
        timeout=20,
        check=False,
    )
    subprocess.run(
        ["systemctl", "start", "ldrs-replay-buffer.service"],
        capture_output=True,
        timeout=30,
        check=False,
    )


def wait_for_hdmi_ring_ready(delay_seconds: float, timeout_s: int = 180) -> bool:
    """Wait until the 4K delayed HDMI HLS playlist is ready."""
    from lib.hdmi_delay_util import hdmi_hls_playlist_ready

    if delay_seconds <= 0:
        return True
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if hdmi_hls_playlist_ready(_system_env()):
            return True
        time.sleep(1)
    return hdmi_hls_playlist_ready(_system_env())


def wait_for_hls_ready(min_segments: int, timeout_s: int = 120) -> bool:
    """Wait until 4K playlist exists with enough segments for delayed HDMI."""
    if min_segments <= 0:
        return True
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if PLAYLIST_4K.is_file() and _segment_count(HLS_4K) >= min_segments:
            return True
        time.sleep(1)
    return PLAYLIST_4K.is_file()


def restart_hdmi_service() -> None:
    """Restart the active HDMI service for the current mode."""
    if not _hdmi_enabled():
        subprocess.run(
            ["systemctl", "stop", "ldrs-hdmi-delay.service", "ldrs-hdmi-live.service"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        return
    if _hdmi_mode() == "live":
        subprocess.run(
            ["systemctl", "restart", "ldrs-hdmi-live.service"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return
    delay = hdmi_delay_seconds(_system_env())
    wait_for_hdmi_ring_ready(delay)
    wait_for_hls_ready(int(delay) + 3)
    subprocess.run(
        ["systemctl", "restart", "ldrs-hdmi-delay.service"],
        capture_output=True,
        timeout=30,
        check=False,
    )


def restart_replay_pipeline() -> None:
    """Stop ingest, wipe buffers, start fresh capture — or HDMI live refresh only."""
    subprocess.run(
        ["/usr/local/bin/ldrs-stop-video-pipelines.sh"],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if hdmi_focus_mode():
        stop_replay_buffer()
        restart_hdmi_service()
    else:
        subprocess.run(
            ["/usr/local/bin/ldrs-clear-hls-buffers.sh"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        start_replay_buffer()
        restart_hdmi_service()
    subprocess.run(
        ["systemctl", "restart", "ldrs-camera-discovery.service"],
        capture_output=True,
        timeout=20,
        check=False,
    )
