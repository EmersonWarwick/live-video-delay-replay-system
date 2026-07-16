"""Wi-Fi network scanning."""
from __future__ import annotations

import time
from typing import List, Optional

from lib.network.adapters import IwAdapter, NmcliAdapter, SystemdAdapter
from lib.network.interfaces import AccessPointService, WifiScanner
from lib.network.models import WifiNetwork, WifiSecurityType
from lib.network.wifi_interface import resolve_wifi_interface


def _map_security(security: str) -> str:
    sec = (security or "").upper()
    if not sec or sec == "--" or "OPEN" in sec:
        return WifiSecurityType.OPEN.value
    if "802.1X" in sec or "EAP" in sec:
        return WifiSecurityType.WPA_EAP.value
    return WifiSecurityType.WPA2_PSK.value


class NmcliWifiScanner(WifiScanner):
    def __init__(
        self,
        nmcli: Optional[NmcliAdapter] = None,
        ap_service: Optional[AccessPointService] = None,
        iw: Optional[IwAdapter] = None,
        systemd: Optional[SystemdAdapter] = None,
    ):
        self._nmcli = nmcli or NmcliAdapter()
        self._ap_service = ap_service
        self._iw = iw or IwAdapter()
        self._systemd = systemd or SystemdAdapter()

    def scan(self) -> List[WifiNetwork]:
        iface = resolve_wifi_interface(self._iw)
        ap_was_active = False
        if self._ap_service and self._ap_service.is_active():
            ap_was_active = True
            self._ap_service.stop()
            time.sleep(2)
        try:
            self._nmcli.enable_nm_management(iface)
            time.sleep(2)
            self._nmcli.set_managed(iface, True)
            self._nmcli.disconnect(iface)
            time.sleep(2)
            self._nmcli.rescan(iface)
            time.sleep(5)
            raw = self._nmcli.device_wifi_list(iface)
            return [
                WifiNetwork(
                    ssid=item["ssid"],
                    security_type=_map_security(item.get("security", "")),
                    signal_strength=int(item.get("signal_strength", 0)),
                    in_use=bool(item.get("in_use")),
                )
                for item in raw
            ]
        finally:
            if ap_was_active and self._ap_service:
                try:
                    self._nmcli.disable_nm_management(iface)
                except Exception:
                    pass
                self._ap_service.start()
