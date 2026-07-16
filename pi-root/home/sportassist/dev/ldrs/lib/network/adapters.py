"""Linux tool adapters — Dependency Inversion."""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Optional


class CommandError(Exception):
    def __init__(self, message: str, returncode: int = 1, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class ShellRunner:
    def run(
        self,
        args: List[str],
        *,
        timeout: int = 60,
        check: bool = True,
        input_text: Optional[str] = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                input=input_text,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandError(f"Command timed out: {' '.join(args)}", returncode=124) from exc
        if check and proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise CommandError(
                err or f"Command failed: {' '.join(args)}",
                returncode=proc.returncode,
                stderr=err,
            )
        return proc


LDRS_CLIENT_CONN = "ldrs-client-wifi"


class NmcliAdapter:
    NM_MANAGED_SCRIPT = "/usr/local/bin/ldrs-wifi-nm-managed.sh"

    def __init__(self, runner: Optional[ShellRunner] = None):
        self._runner = runner or ShellRunner()
        self.last_error = ""

    def _fail(self, proc: subprocess.CompletedProcess[str], action: str) -> bool:
        err = (proc.stderr or proc.stdout or "").strip()
        self.last_error = err or f"{action} failed"
        return False

    def enable_nm_management(self, iface: str) -> None:
        self._runner.run([self.NM_MANAGED_SCRIPT, "enable", iface], timeout=20, check=False)

    def disable_nm_management(self, iface: str) -> None:
        self._runner.run([self.NM_MANAGED_SCRIPT, "disable", iface], timeout=20, check=False)

    def available(self) -> bool:
        proc = self._runner.run(["which", "nmcli"], check=False)
        return proc.returncode == 0

    def device_wifi_list(self, iface: str) -> List[Dict[str, Any]]:
        proc = self._runner.run(
            ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", iface],
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return []
        networks: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            # nmcli -t uses ':' separators; SSID is field 2 (IN-USE, SSID, SIGNAL, SECURITY)
            parts = line.split(":")
            if len(parts) < 4:
                continue
            in_use, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            try:
                sig = int(signal)
            except ValueError:
                sig = 0
            networks.append(
                {
                    "ssid": ssid,
                    "signal_strength": sig,
                    "security": security or "open",
                    "in_use": in_use == "*",
                }
            )
        return sorted(networks, key=lambda n: n["signal_strength"], reverse=True)

    def rescan(self, iface: str) -> None:
        self._runner.run(
            ["nmcli", "dev", "wifi", "rescan", "ifname", iface],
            timeout=20,
            check=False,
        )

    def set_managed(self, iface: str, managed: bool) -> None:
        flag = "yes" if managed else "no"
        self._runner.run(["nmcli", "dev", "set", iface, "managed", flag], check=False)

    def disconnect(self, iface: str) -> None:
        self._runner.run(["nmcli", "dev", "disconnect", iface], check=False)

    def delete_connection(self, name: str) -> None:
        self._runner.run(["nmcli", "connection", "delete", name], check=False)

    def delete_connection(self, name: str) -> None:
        self._runner.run(["nmcli", "connection", "delete", name], check=False)

    def _prepare_client_connection(
        self, iface: str, ssid: str, security: str, password: str, username: str
    ) -> bool:
        self.delete_connection(LDRS_CLIENT_CONN)
        self.delete_connection(ssid)
        base = [
            "nmcli",
            "connection",
            "add",
            "type",
            "wifi",
            "con-name",
            LDRS_CLIENT_CONN,
            "ifname",
            iface,
            "ssid",
            ssid,
        ]
        sec = (security or "").lower()
        if sec == "open":
            args = base + ["wifi-sec.key-mgmt", "none"]
        elif sec == "wpa-eap":
            args = base + [
                "wifi-sec.key-mgmt",
                "wpa-eap",
                "802-1x.eap",
                "peap",
                "802-1x.identity",
                username,
                "802-1x.password",
                password,
            ]
        else:
            args = base + ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
        proc = self._runner.run(args, timeout=30, check=False)
        if proc.returncode != 0:
            return self._fail(proc, "create_connection")
        up = self._runner.run(
            ["nmcli", "-w", "45", "connection", "up", LDRS_CLIENT_CONN],
            timeout=50,
            check=False,
        )
        if up.returncode != 0:
            return self._fail(up, "activate_connection")
        self.last_error = ""
        return True

    def connect_psk(self, iface: str, ssid: str, password: str) -> bool:
        return self._prepare_client_connection(iface, ssid, "wpa2-psk", password, "")

    def connect_open(self, iface: str, ssid: str) -> bool:
        return self._prepare_client_connection(iface, ssid, "open", "", "")

    def connect_eap(self, iface: str, ssid: str, username: str, password: str) -> bool:
        return self._prepare_client_connection(iface, ssid, "wpa-eap", password, username)

    def connection_state(self, iface: str) -> str:
        proc = self._runner.run(
            ["nmcli", "-t", "-f", "GENERAL.STATE", "dev", "show", iface],
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GENERAL.STATE:"):
                return line.split(":", 1)[1].strip()
        return ""

    def active_ssid(self, iface: str) -> str:
        proc = self._runner.run(
            ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "dev", "show", iface],
            check=False,
        )
        conn = ""
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GENERAL.CONNECTION:"):
                conn = line.split(":", 1)[1].strip()
        if not conn or conn == "--":
            return ""
        proc2 = self._runner.run(
            ["nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", conn],
            check=False,
        )
        for line in (proc2.stdout or "").splitlines():
            if line.startswith("802-11-wireless.ssid:"):
                return line.split(":", 1)[1].strip()
        return ""

    def signal_strength(self, iface: str) -> Optional[int]:
        proc = self._runner.run(
            ["nmcli", "-t", "-f", "WLAN-SIGNAL", "dev", "wifi", "list", "ifname", iface],
            check=False,
        )
        best = None
        for line in (proc.stdout or "").splitlines():
            m = re.search(r":(\d+)$", line)
            if m:
                val = int(m.group(1))
                if best is None or val > best:
                    best = val
        return best


class SystemdAdapter:
    def __init__(self, runner: Optional[ShellRunner] = None):
        self._runner = runner or ShellRunner()

    def is_active(self, unit: str) -> bool:
        proc = self._runner.run(["systemctl", "is-active", unit], check=False)
        return proc.stdout.strip() == "active"

    def start(self, unit: str) -> bool:
        proc = self._runner.run(["systemctl", "start", unit], check=False)
        return proc.returncode == 0

    def stop(self, unit: str) -> bool:
        proc = self._runner.run(["systemctl", "stop", unit], check=False)
        return proc.returncode == 0

    def restart(self, unit: str) -> bool:
        proc = self._runner.run(["systemctl", "restart", unit], check=False)
        return proc.returncode == 0


class IwAdapter:
    def __init__(self, runner: Optional[ShellRunner] = None):
        self._runner = runner or ShellRunner()

    def list_wlan_interfaces(self) -> List[str]:
        proc = self._runner.run(["iw", "dev"], check=False)
        ifaces: List[str] = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("Interface "):
                ifaces.append(line.split()[1])
        return ifaces

    def interface_mode(self, iface: str) -> str:
        proc = self._runner.run(["iw", "dev", iface, "info"], check=False)
        for line in (proc.stdout or "").splitlines():
            if "type" in line:
                parts = line.strip().split()
                if "type" in parts:
                    idx = parts.index("type")
                    if idx + 1 < len(parts):
                        return parts[idx + 1]
        return ""

    def driver_for_iface(self, iface: str) -> str:
        proc = self._runner.run(
            ["bash", "-c", f"basename $(readlink -f /sys/class/net/{iface}/device/driver 2>/dev/null)"],
            check=False,
        )
        return (proc.stdout or "").strip()


class StateFileAdapter:
    def __init__(self, path: str = "/run/sportassist/network-state.json"):
        self._path = path

    def read(self) -> Dict[str, Any]:
        try:
            from pathlib import Path

            p = Path(self._path)
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def write(self, data: Dict[str, Any]) -> None:
        from pathlib import Path

        p = Path(self._path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
