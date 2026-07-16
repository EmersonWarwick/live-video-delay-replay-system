"""Network status reporting."""
from __future__ import annotations

import socket
import subprocess
from typing import Optional

from lib.network.access_point_service import ShellAccessPointService
from lib.network.adapters import StateFileAdapter
from lib.network.client_wifi_service import NmcliClientWifiService
from lib.network.hostname_service import AvahiHostnameService
from lib.network.interfaces import NetworkStatusProvider
from lib.network.models import NetworkState, NetworkStatus
from lib.network.repository import FileNetworkConfigRepository
from lib.network.ssh_endpoints import get_ssh_endpoints
from lib.network.wifi_interface import resolve_wifi_interface
from lib.status_util import camera_connected, replay_buffer_active

CAMERA_ENV = "/etc/sportassist/camera.env"


class LiveNetworkStatusProvider(NetworkStatusProvider):
    def __init__(
        self,
        repository: Optional[FileNetworkConfigRepository] = None,
        ap_service: Optional[ShellAccessPointService] = None,
        client_service: Optional[NmcliClientWifiService] = None,
        hostname_service: Optional[AvahiHostnameService] = None,
        state_file: Optional[StateFileAdapter] = None,
    ):
        self._repo = repository or FileNetworkConfigRepository()
        self._ap = ap_service or ShellAccessPointService()
        self._client = client_service or NmcliClientWifiService()
        self._hostname = hostname_service or AvahiHostnameService()
        self._state = state_file or StateFileAdapter()

    def get_status(self) -> NetworkStatus:
        config = self._repo.load()
        saved = self._state.read()
        state_str = saved.get("state", NetworkState.UNKNOWN.value)
        try:
            state = NetworkState(state_str)
        except ValueError:
            state = NetworkState.UNKNOWN

        try:
            iface = resolve_wifi_interface()
        except RuntimeError:
            iface = ""

        ap_active = self._ap.is_active()
        client_active = self._client.is_connected()
        connected_ssid = ""
        signal = None
        ip_addr = self._primary_ip()
        if client_active:
            wip = self._interface_ip(iface)
            if wip:
                ip_addr = wip
        elif ap_active:
            ap_ip = self._interface_ip(iface)
            if ap_ip:
                ip_addr = ap_ip
        mode = "ap" if config.use_local_access_point else "client"

        if ap_active:
            state = NetworkState.AP_ACTIVE
            mode = "ap"
            connected_ssid = config.local_ap_ssid
        elif client_active:
            state = NetworkState.CLIENT_WIFI_ACTIVE
            mode = "client"
            connected_ssid = self._client.connected_ssid() or config.client_wifi_ssid
            signal = self._client.signal_strength()
        elif state == NetworkState.CLIENT_WIFI_CONNECTING:
            mode = "client"
        elif not config.use_local_access_point and state in (
            NetworkState.CLIENT_WIFI_FAILED,
            NetworkState.FALLBACK_TO_AP,
        ):
            mode = "client"

        hostname = config.device_hostname or self._hostname.current_hostname()
        client_status = "connected" if client_active else (
            "connecting" if state == NetworkState.CLIENT_WIFI_CONNECTING else "disconnected"
        )

        ssh_endpoints = get_ssh_endpoints()

        return NetworkStatus(
            state=state,
            mode=mode,
            connected_ssid=connected_ssid,
            ip_address=ip_addr,
            signal_strength=signal,
            hostname=hostname,
            ap_active=ap_active,
            client_wifi_active=client_active,
            client_wifi_status=client_status,
            camera_connected=camera_connected(),
            replay_service_active=replay_buffer_active(),
            interface=iface,
            ssh_endpoints=ssh_endpoints,
        )

    def _interface_ip(self, iface: str) -> str:
        if not iface:
            return ""
        try:
            proc = subprocess.run(
                ["ip", "-4", "-br", "addr", "show", iface],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            parts = (proc.stdout or "").split()
            for part in parts:
                if "/" in part and not part.startswith("127."):
                    return part.split("/")[0]
        except Exception:
            pass
        return ""

    def _primary_ip(self) -> str:
        try:
            proc = subprocess.run(
                ["hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            parts = (proc.stdout or "").split()
            for addr in parts:
                if not addr.startswith("127.") and not addr.startswith("169.254."):
                    return addr
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return ""
