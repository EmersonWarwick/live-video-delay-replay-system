"""Read active HDMI display mode (KMS) for settings status."""
from __future__ import annotations

import re
import subprocess
from typing import Dict, Optional


def read_hdmi_display_mode() -> Dict[str, Optional[str]]:
    """Return active width/height/refresh on the first connected HDMI-A connector."""
    try:
        proc = subprocess.run(
            ["kmsprint"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _empty()

    text = proc.stdout or ""
    in_hdmi = False
    for line in text.splitlines():
        if re.search(r"HDMI-A-\d+ \(connected\)", line):
            in_hdmi = True
            continue
        if in_hdmi and re.match(r"Connector \d+", line):
            break
        if not in_hdmi:
            continue
        m = re.search(r"Crtc \d+ \(\d+\) (\d+)x(\d+)@([\d.]+)", line)
        if m:
            return {
                "width": m.group(1),
                "height": m.group(2),
                "refresh_hz": m.group(3),
            }
    return _empty()


def format_hdmi_display_mode(mode: Dict[str, Optional[str]]) -> str:
    w, h, hz = mode.get("width"), mode.get("height"), mode.get("refresh_hz")
    if w and h:
        suffix = f" @ {hz} Hz" if hz else ""
        return f"{w}×{h}{suffix}"
    return "unknown"


def _empty() -> Dict[str, Optional[str]]:
    return {"width": None, "height": None, "refresh_hz": None}
