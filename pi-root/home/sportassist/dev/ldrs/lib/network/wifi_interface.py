"""Resolve the Wi‑Fi interface used for AP / client mode (Pi built-in radio)."""
from __future__ import annotations

from typing import Optional

from lib.network.adapters import IwAdapter


def resolve_wifi_interface(iw: Optional[IwAdapter] = None) -> str:
    iw = iw or IwAdapter()
    ifaces = iw.list_wlan_interfaces()
    for iface in ifaces:
        driver = iw.driver_for_iface(iface)
        if driver == "brcmfmac":
            return iface
    if len(ifaces) == 1:
        return ifaces[0]
    raise RuntimeError(
        "No Raspberry Pi built-in Wi‑Fi interface found (brcmfmac). "
        "Check that dtoverlay=disable-wifi-pi5 is not set in /boot/firmware/config.txt"
    )
