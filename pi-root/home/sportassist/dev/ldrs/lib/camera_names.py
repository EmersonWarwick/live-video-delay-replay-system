"""Sport Assist camera hostname matching — spec-camera-discovery.md §2."""
from __future__ import annotations

import re

PATTERNS = (
    re.compile(r"^SportAssist", re.I),
    re.compile(r"^sport-assist", re.I),
    re.compile(r"^sportassist", re.I),
)

_DISCOVERED_HOSTNAME = re.compile(r"^(onvif|rtsp)-", re.I)
_PLAUSIBLE_HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def is_sport_assist_name(name: str) -> bool:
    if not name:
        return False
    if any(p.search(name) for p in PATTERNS):
        return True
    return "sport assist" in name.lower()


def is_acceptable_camera_hostname(name: str) -> bool:
    """Hostname allowed when saving camera config (commissioning)."""
    name = canonical_hostname(name)
    if not name or len(name) > 63:
        return False
    if is_sport_assist_name(name):
        return True
    if _DISCOVERED_HOSTNAME.match(name):
        return True
    low = name.lower()
    if "://" in name or low.startswith("http") or ".wsdl" in low or "onvif.org" in low:
        return False
    return bool(_PLAUSIBLE_HOSTNAME.match(name))


def canonical_hostname(name: str) -> str:
    return name.strip()
