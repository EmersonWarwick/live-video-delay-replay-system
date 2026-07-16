"""SSH reachability hints for eth0 and wlan0."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from lib.env_util import load_env

SSH_ENDPOINTS_PATH = Path("/run/sportassist/ssh-endpoints.json")
NETWORK_ENV = "/etc/sportassist/network.env"
SYSTEM_ENV = "/etc/sportassist/system.env"


def _iface_ipv4(iface: str) -> str:
    try:
        proc = subprocess.run(
            ["ip", "-4", "-br", "addr", "show", iface],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for part in (proc.stdout or "").split():
            if "/" in part and not part.startswith("127."):
                return part.split("/")[0]
    except Exception:
        pass
    return ""


def _hostapd_active() -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "hostapd"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (proc.stdout or "").strip() == "active"
    except Exception:
        return False


def _sshd_active() -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", "ssh"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if (proc.stdout or "").strip() == "active":
            return True
        proc = subprocess.run(
            ["systemctl", "is-active", "sshd"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (proc.stdout or "").strip() == "active"
    except Exception:
        return False


def _ssh_enabled() -> bool:
    try:
        sys_env = load_env(Path(SYSTEM_ENV))
        return sys_env.get("SSH_ENABLED", "1") == "1"
    except Exception:
        return True


def compute_ssh_endpoints() -> Dict[str, Any]:
    eth_ip = _iface_ipv4("eth0")
    wlan_ip = _iface_ipv4("wlan0")
    ap_active = _hostapd_active()
    ap_ip = wlan_ip if ap_active else ""
    if ap_active and not ap_ip:
        ap_ip = "192.168.4.1"

    try:
        net = load_env(Path(NETWORK_ENV))
    except Exception:
        net = {}
    direct_mode = net.get("ETH_CAMERA_DHCP", "1") == "1"

    if eth_ip:
        eth_hint = f"ssh sportassist@{eth_ip}"
    elif direct_mode:
        eth_hint = "ssh sportassist@192.168.10.1 (Direct/PoE on eth0)"
    else:
        eth_hint = "ssh sportassist@<eth0 IP> or sport-assist.local (Customer LAN)"

    if wlan_ip:
        wlan_hint = f"ssh sportassist@{wlan_ip}"
    elif ap_active:
        wlan_hint = f"ssh sportassist@{ap_ip} (AP mode)"
    else:
        wlan_hint = "Join AP or client Wi‑Fi for wlan SSH"

    sshd_on = _ssh_enabled() and _sshd_active()
    if not sshd_on:
        eth_hint = "SSH disabled in Settings"
        wlan_hint = "SSH disabled in Settings"

    return {
        "sshdActive": sshd_on,
        "hostname": "sport-assist.local",
        "eth0": {
            "ip": eth_ip,
            "sshAvailable": bool(eth_ip) and sshd_on,
            "mode": "direct" if direct_mode else "customer_lan",
            "hint": eth_hint,
        },
        "wlan0": {
            "ip": wlan_ip,
            "sshAvailable": bool(wlan_ip) and sshd_on,
            "apActive": ap_active,
            "apIp": ap_ip,
            "hint": wlan_hint,
        },
    }


def get_ssh_endpoints() -> Dict[str, Any]:
    if SSH_ENDPOINTS_PATH.is_file():
        try:
            data = json.loads(SSH_ENDPOINTS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "eth0" in data:
                return data
        except Exception:
            pass
    return compute_ssh_endpoints()
