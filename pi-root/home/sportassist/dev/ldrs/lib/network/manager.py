"""NetworkManager facade — coordinates network mode changes."""
from __future__ import annotations

import subprocess
from typing import Any, Dict, List

from lib.network.access_point_service import ShellAccessPointService
from lib.network.adapters import StateFileAdapter
from lib.network.commands import (
    ApplyNetworkSettingsCommand,
    FallbackService,
    ForgetWifiCredentialsCommand,
    SaveNetworkSettingsCommand,
    SetDeviceHostnameCommand,
    SwitchToApModeCommand,
    SwitchToClientWifiCommand,
)
from lib.network.hostname_service import AvahiHostnameService
from lib.network.models import NetworkConfig
from lib.network.repository import FileNetworkConfigRepository
from lib.network.status_provider import LiveNetworkStatusProvider
from lib.network.validation import validate_save_payload
from lib.network.wifi_scanner import NmcliWifiScanner


class NetworkManager:
    """Facade for web UI and CLI."""

    def __init__(self):
        self._repo = FileNetworkConfigRepository()
        self._hostname = AvahiHostnameService()
        self._state = StateFileAdapter()
        self._ap = ShellAccessPointService()
        self._fallback = FallbackService(self._repo, self._ap, self._state)
        self._status = LiveNetworkStatusProvider(
            repository=self._repo,
            ap_service=self._ap,
            state_file=self._state,
        )
        self._scanner = NmcliWifiScanner(ap_service=self._ap)

    def get_config(self) -> Dict[str, Any]:
        return self._repo.load().public_dict()

    def get_status(self) -> Dict[str, Any]:
        return self._status.get_status().to_dict()

    def scan_wifi(self) -> Dict[str, Any]:
        try:
            networks = [n.to_dict() for n in self._scanner.scan()]
            return {"ok": True, "networks": networks}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "networks": []}

    def save_settings(self, payload: dict) -> Dict[str, Any]:
        existing = self._repo.load()
        config, errors = validate_save_payload(payload, existing)
        if errors:
            return {"ok": False, "errors": errors}
        return SaveNetworkSettingsCommand(self._repo, config).execute()

    def set_device_hostname(self, hostname: str) -> Dict[str, Any]:
        return SetDeviceHostnameCommand(self._repo, self._hostname, hostname).execute()

    def apply_settings(self) -> Dict[str, Any]:
        return ApplyNetworkSettingsCommand(
            self._repo, self._hostname, self._state, self._fallback
        ).execute()

    def switch_to_ap(self) -> Dict[str, Any]:
        return SwitchToApModeCommand(self._repo, self._hostname).execute()

    def switch_to_client_wifi(self) -> Dict[str, Any]:
        return SwitchToClientWifiCommand(
            self._repo, self._hostname, self._fallback
        ).execute()

    def forget_credentials(self) -> Dict[str, Any]:
        return ForgetWifiCredentialsCommand(self._repo, self._ap).execute()

    def export_logs(self) -> str:
        units = [
            "hostapd",
            "dnsmasq",
            "avahi-daemon",
            "NetworkManager",
            "ldrs-wifi-ap.service",
            "ldrs-wifi-network.service",
            "ldrs-web.service",
        ]
        lines: List[str] = ["=== Sport Assist Network Diagnostics ===", ""]
        for unit in units:
            lines.append(f"--- journalctl -u {unit} (last 80 lines) ---")
            proc = subprocess.run(
                ["journalctl", "-u", unit, "-b", "-n", "80", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            lines.append(proc.stdout or proc.stderr or "(no output)")
            lines.append("")
        lines.append("--- nmcli dev status ---")
        proc = subprocess.run(
            ["nmcli", "dev", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        lines.append(proc.stdout or proc.stderr or "")
        lines.append("--- iw dev ---")
        proc = subprocess.run(["iw", "dev"], capture_output=True, text=True, check=False)
        lines.append(proc.stdout or proc.stderr or "")
        return "\n".join(lines)

    def boot_apply(self) -> Dict[str, Any]:
        config = self._repo.load()
        self._hostname.apply(config.device_hostname)
        if config.use_local_access_point:
            return SwitchToApModeCommand(self._repo, self._hostname).execute()
        result = SwitchToClientWifiCommand(
            self._repo, self._hostname, self._fallback
        ).execute()
        return result
