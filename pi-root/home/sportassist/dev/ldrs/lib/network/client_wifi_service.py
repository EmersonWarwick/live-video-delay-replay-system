"""Client building Wi-Fi connection — wlan0 only via wpa_supplicant."""
from __future__ import annotations

import subprocess
from typing import Optional

from lib.network.adapters import NmcliAdapter
from lib.network.interfaces import ClientWifiService
from lib.network.models import NetworkConfig, WifiSecurityType
from lib.network.wifi_interface import resolve_wifi_interface

CONNECT_SCRIPT = "/usr/local/bin/ldrs-wifi-client-connect.sh"
DISCONNECT_SCRIPT = "/usr/local/bin/ldrs-wifi-client-disconnect.sh"


class NmcliClientWifiService(ClientWifiService):
    def __init__(self, nmcli: Optional[NmcliAdapter] = None):
        self._nmcli = nmcli or NmcliAdapter()
        self._iface = ""
        self.last_error = ""

    def _ensure_iface(self) -> str:
        if not self._iface:
            self._iface = resolve_wifi_interface()
        return self._iface

    def connect(self, config: NetworkConfig, timeout_seconds: int = 90) -> bool:
        self.last_error = ""
        iface = self._ensure_iface()
        security = (config.client_wifi_security_type or WifiSecurityType.WPA2_PSK.value).lower()
        if security == WifiSecurityType.WPA_EAP.value:
            psk = f"{config.client_wifi_username}|{config.client_wifi_password}"
        elif security == WifiSecurityType.OPEN.value:
            psk = ""
        else:
            psk = config.client_wifi_password

        try:
            proc = subprocess.run(
                [CONNECT_SCRIPT, config.client_wifi_ssid, psk, security, iface],
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 75),
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.last_error = "wifi_connect_timeout"
            return False

        if proc.returncode != 0:
            self.last_error = (proc.stderr or proc.stdout or "wifi_connect_failed").strip()
            return False
        return self.is_connected()

    def disconnect(self) -> bool:
        iface = self._ensure_iface()
        subprocess.run([DISCONNECT_SCRIPT, iface], capture_output=True, timeout=30, check=False)
        return True

    def is_connected(self) -> bool:
        iface = self._ensure_iface()
        try:
            link = subprocess.run(
                ["iw", "dev", iface, "link"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if "Connected to" not in (link.stdout or ""):
                return False
            ip_proc = subprocess.run(
                ["ip", "-4", "-br", "addr", "show", iface],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            line = (ip_proc.stdout or "").strip()
            return bool(line and ("192.168." in line or "10." in line or "172." in line))
        except Exception:
            return False

    def connected_ssid(self) -> str:
        iface = self._ensure_iface()
        try:
            proc = subprocess.run(
                ["iw", "dev", iface, "link"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for part in (proc.stdout or "").split():
                if part.startswith("SSID:"):
                    return part.split(":", 1)[1]
        except Exception:
            pass
        return ""

    def signal_strength(self) -> Optional[int]:
        iface = self._ensure_iface()
        try:
            proc = subprocess.run(
                ["iw", "dev", iface, "link"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for part in (proc.stdout or "").split():
                if part.startswith("signal:"):
                    val = part.split(":")[1].replace("dBm", "").strip()
                    # rough map dBm to %
                    dbm = int(val)
                    return max(0, min(100, 2 * (dbm + 100)))
        except Exception:
            pass
        return self._nmcli.signal_strength(iface)
