"""mDNS / Avahi hostname management."""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Optional

from lib.network.adapters import SystemdAdapter
from lib.network.interfaces import HostnameService

AVAHI_CONF = Path("/etc/avahi/avahi-daemon.conf")


class AvahiHostnameService(HostnameService):
    def __init__(self, systemd: Optional[SystemdAdapter] = None):
        self._systemd = systemd or SystemdAdapter()

    def _bare_hostname(self, hostname: str) -> str:
        return (hostname or "sport-assist").removesuffix(".local").strip() or "sport-assist"

    def apply(self, hostname: str, *, restart_avahi: bool = True) -> bool:
        bare = self._bare_hostname(hostname)
        try:
            Path("/etc/hostname").write_text(bare + "\n", encoding="utf-8")
            subprocess.run(["hostnamectl", "set-hostname", bare], check=False, timeout=15)
        except OSError:
            return False
        self._ensure_avahi_host_name(bare)
        if restart_avahi:
            self._systemd.restart("avahi-daemon")
        hosts_line = f"127.0.1.1\t{bare}\n"
        hosts_path = Path("/etc/hosts")
        try:
            lines = hosts_path.read_text(encoding="utf-8").splitlines()
            filtered = [ln for ln in lines if "127.0.1.1" not in ln or bare not in ln]
            if not any(bare in ln for ln in filtered):
                filtered.append(hosts_line.strip())
            hosts_path.write_text("\n".join(filtered) + "\n", encoding="utf-8")
        except OSError:
            pass
        return True

    def _ensure_avahi_host_name(self, bare: str) -> None:
        if not AVAHI_CONF.is_file():
            return
        text = AVAHI_CONF.read_text(encoding="utf-8")
        if "host-name=" in text:
            import re

            text = re.sub(r"^host-name=.*$", f"host-name={bare}", text, flags=re.M)
        else:
            text = text.rstrip() + f"\nhost-name={bare}\n"
        AVAHI_CONF.write_text(text, encoding="utf-8")

    def current_hostname(self) -> str:
        try:
            return socket.gethostname() + ".local"
        except Exception:
            return "sport-assist.local"
