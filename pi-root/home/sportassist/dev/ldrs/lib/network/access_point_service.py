"""Access Point mode control."""
from __future__ import annotations

import subprocess
from typing import Optional

from lib.network.adapters import IwAdapter, SystemdAdapter
from lib.network.interfaces import AccessPointService


class ShellAccessPointService(AccessPointService):
    AP_SCRIPT = "/usr/local/bin/ldrs-wifi-ap.sh"
    STOP_SCRIPT = "/usr/local/bin/ldrs-wifi-ap-stop.sh"

    def __init__(
        self,
        systemd: Optional[SystemdAdapter] = None,
        iw: Optional[IwAdapter] = None,
    ):
        self._systemd = systemd or SystemdAdapter()
        self._iw = iw or IwAdapter()

    def start(self) -> bool:
        iface = ""
        try:
            from lib.network.wifi_interface import resolve_wifi_interface
            iface = resolve_wifi_interface()
            subprocess.run(
                ["/usr/local/bin/ldrs-wifi-client-disconnect.sh", iface],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except Exception:
            pass
        proc = subprocess.run(
            [self.AP_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode == 0

    def stop(self, *, hostapd_only: bool = True) -> bool:
        args = [self.STOP_SCRIPT, "hostapd-only" if hostapd_only else "full"]
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return proc.returncode == 0

    def is_active(self) -> bool:
        if self._systemd.is_active("hostapd"):
            return True
        for iface in self._iw.list_wlan_interfaces():
            if self._iw.interface_mode(iface) == "AP":
                return True
        return False
