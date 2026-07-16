"""Input validation for network settings."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from lib.network.models import NetworkConfig, WifiSecurityType

_SSID_RE = re.compile(r"^[\x20-\x7E]{1,32}$")
_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.local)?$"
)
_SECURITY_TYPES = {t.value for t in WifiSecurityType}


def validate_ssid(ssid: str) -> Optional[str]:
    ssid = (ssid or "").strip()
    if not ssid:
        return "SSID is required"
    if not _SSID_RE.match(ssid):
        return "SSID must be 1–32 printable ASCII characters"
    return None


def validate_password(password: str, security_type: str, *, required: bool) -> Optional[str]:
    security = (security_type or WifiSecurityType.WPA2_PSK.value).lower()
    if security == WifiSecurityType.OPEN.value:
        return None
    if not password and required:
        return "Password is required for this security type"
    if password and len(password) < 8:
        return "Password must be at least 8 characters"
    if password and len(password) > 63:
        return "Password must be at most 63 characters"
    return None


def validate_username(username: str, security_type: str) -> Optional[str]:
    security = (security_type or "").lower()
    if security != WifiSecurityType.WPA_EAP.value:
        return None
    username = (username or "").strip()
    if not username:
        return "Username is required for enterprise Wi-Fi"
    if len(username) > 128:
        return "Username is too long"
    return None


def validate_hostname(hostname: str) -> Optional[str]:
    hostname = (hostname or "").strip().lower()
    if not hostname:
        return "Hostname is required"
    bare = hostname.removesuffix(".local")
    if not _HOSTNAME_RE.match(hostname) and not _HOSTNAME_RE.match(bare):
        return "Invalid hostname (use letters, numbers, hyphens; e.g. sport-assist.local)"
    return None


def validate_security_type(security_type: str) -> Optional[str]:
    if (security_type or "").lower() not in _SECURITY_TYPES:
        return f"Security type must be one of: {', '.join(sorted(_SECURITY_TYPES))}"
    return None


def validate_config(
    config: NetworkConfig,
    *,
    require_client_credentials: bool = False,
) -> List[str]:
    errors: List[str] = []
    host_err = validate_hostname(config.device_hostname)
    if host_err:
        errors.append(host_err)
    sec_err = validate_security_type(config.client_wifi_security_type)
    if sec_err:
        errors.append(sec_err)
    if not config.use_local_access_point or require_client_credentials:
        ssid_err = validate_ssid(config.client_wifi_ssid)
        if ssid_err:
            errors.append(ssid_err)
        user_err = validate_username(
            config.client_wifi_username, config.client_wifi_security_type
        )
        if user_err:
            errors.append(user_err)
        pass_err = validate_password(
            config.client_wifi_password,
            config.client_wifi_security_type,
            required=require_client_credentials
            and config.client_wifi_security_type != WifiSecurityType.OPEN.value,
        )
        if pass_err:
            errors.append(pass_err)
    if config.fallback_timeout_seconds < 60 or config.fallback_timeout_seconds > 120:
        errors.append("Fallback timeout must be 60–120 seconds")
    return errors


def validate_save_payload(
    payload: dict, existing: NetworkConfig
) -> Tuple[Optional[NetworkConfig], List[str]]:
    """Merge API payload with existing config (preserve passwords when omitted)."""
    use_ap = payload.get("useLocalAccessPoint", existing.use_local_access_point)
    if isinstance(use_ap, str):
        use_ap = use_ap.lower() in ("1", "true", "yes")
    security = (
        payload.get("clientWifiSecurityType") or existing.client_wifi_security_type
    ).lower()
    client_pass = payload.get("clientWifiPassword")
    if client_pass is None or client_pass == "":
        client_pass = existing.client_wifi_password
    config = NetworkConfig(
        use_local_access_point=bool(use_ap),
        local_ap_ssid=payload.get("localApSsid", existing.local_ap_ssid),
        local_ap_password=existing.local_ap_password,
        client_wifi_ssid=(payload.get("clientWifiSsid") or existing.client_wifi_ssid).strip(),
        client_wifi_username=(
            payload.get("clientWifiUsername") or existing.client_wifi_username
        ).strip(),
        client_wifi_password=client_pass or "",
        client_wifi_security_type=security,
        device_hostname=(
            payload.get("deviceHostname") or existing.device_hostname
        ).strip(),
        fallback_timeout_seconds=int(
            payload.get("fallbackTimeoutSeconds", existing.fallback_timeout_seconds)
        ),
    )
    require_creds = not config.use_local_access_point
    return config, validate_config(config, require_client_credentials=require_creds)
