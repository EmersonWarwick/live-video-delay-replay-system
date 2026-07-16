"""Generate assigned camera identity and provision via ONVIF Device Management."""
from __future__ import annotations

import secrets
import string
from typing import Any, Iterable, List

ASSIGNED_USERNAME = "sportassist"
ASSIGNED_HOSTNAME = "SportAssistCam"


def generate_assigned_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_assigned_hostname(name: str) -> bool:
    return (name or "").strip().lower() == ASSIGNED_HOSTNAME.lower()


def _user_list(users_response: Any) -> List[Any]:
    users = getattr(users_response, "User", None)
    if users is None:
        return []
    if not isinstance(users, list):
        return [users]
    return users


def _usernames(users_response: Any) -> Iterable[str]:
    for user in _user_list(users_response):
        name = getattr(user, "Username", None) or ""
        if name:
            yield str(name)


def provision_assigned_user(cam: Any, username: str, password: str) -> None:
    """Create or update sportassist administrator on the camera."""
    dev = cam.create_devicemgmt_service()
    user_def = {
        "Username": username,
        "Password": password,
        "UserLevel": "Administrator",
    }
    existing = set(_usernames(dev.GetUsers()))
    if username in existing:
        dev.SetUser({"User": user_def})
        return
    try:
        dev.CreateUsers({"User": user_def})
    except Exception:
        dev.SetUser({"User": user_def})


def set_camera_hostname_onvif(cam: Any, hostname: str) -> bool:
    """Best-effort ONVIF hostname — Pi always stores hostname in camera.env."""
    try:
        net = cam.create_network_service()
        if hasattr(net, "SetHostname"):
            net.SetHostname({"Name": hostname})
            return True
    except Exception:
        pass
    return False
