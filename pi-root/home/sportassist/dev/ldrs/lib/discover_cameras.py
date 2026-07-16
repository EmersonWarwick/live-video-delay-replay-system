#!/usr/bin/env python3
"""Discover cameras — direct DHCP leases or customer LAN (ONVIF + RTSP)."""
from __future__ import annotations

import json
import ipaddress
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.camera_names import is_sport_assist_name
from lib.env_util import SPORTASSIST_ETC, load_env
from lib.onvif_client import is_plausible_camera_hostname, onvif_available, ws_discover

RTSP_PORT = 554
DNSMASQ_LEASES = Path("/var/lib/misc/dnsmasq.leases")
_AP_WIFI_IP = "192.168.4.1"


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return True


def is_appliance_host(ip: str, hostname: str, pi_static_ip: str = "192.168.10.1") -> bool:
    """True for the Pi itself — never a PoE camera."""
    if _is_loopback(ip):
        return True
    if ip in (pi_static_ip, _AP_WIFI_IP):
        return True
    host = (hostname or "").strip().lower()
    if host in ("sport-assist", "localhost", "sportassist"):
        return True
    try:
        if host == socket.gethostname().lower():
            return True
    except OSError:
        pass
    return False


def filter_cameras(
    cameras: List[Dict[str, Any]], pi_static_ip: str = "192.168.10.1"
) -> List[Dict[str, Any]]:
    return [
        c
        for c in cameras
        if not is_appliance_host(c.get("ip", ""), c.get("hostname", ""), pi_static_ip)
    ]


def camera_subnet(pi_static_ip: str = "192.168.10.1") -> ipaddress.IPv4Network:
    return ipaddress.ip_network(f"{pi_static_ip}/24", strict=False)


def ip_in_camera_subnet(ip: str, pi_static_ip: str = "192.168.10.1") -> bool:
    try:
        return ipaddress.ip_address(ip) in camera_subnet(pi_static_ip)
    except ValueError:
        return False


def ip_from_xaddr(xaddr: str) -> str:
    parsed = urlparse(xaddr if "://" in xaddr else f"http://{xaddr}")
    return parsed.hostname or ""


def port_from_xaddr(xaddr: str) -> int:
    parsed = urlparse(xaddr if "://" in xaddr else f"http://{xaddr}")
    return parsed.port or 80


def camera_entry(
    hostname: str,
    ip: str,
    *,
    onvif: bool,
    source: str,
    onvif_port: int = 80,
) -> Dict[str, Any]:
    return {
        "hostname": hostname,
        "ip": ip,
        "onvif": onvif,
        "onvifPort": onvif_port if onvif else 80,
        "rtspPort": RTSP_PORT,
        "source": source,
    }


def hostname_for_discovered_camera(ip: str, ws_label: str = "") -> str:
    """Pick a user-facing hostname — never an ONVIF type/scope URL."""
    ws_label = (ws_label or "").strip()
    if ws_label and is_sport_assist_name(ws_label):
        return ws_label
    try:
        rdns = socket.getfqdn(ip).split(".")[0]
    except Exception:
        rdns = ""
    if rdns and rdns != ip and is_sport_assist_name(rdns):
        return rdns
    if ws_label and is_plausible_camera_hostname(ws_label):
        return ws_label[:48]
    if rdns and rdns != ip and is_plausible_camera_hostname(rdns):
        return rdns
    return f"onvif-{ip.replace('.', '-')}"


def discover_dhcp_leases(pi_static_ip: str = "192.168.10.1") -> List[Dict[str, Any]]:
    """Direct mode: cameras leased by Pi dnsmasq on eth0 (192.168.10.x only)."""
    found: List[Dict[str, Any]] = []
    if not DNSMASQ_LEASES.is_file():
        return found
    subnet = camera_subnet(pi_static_ip)
    for line in DNSMASQ_LEASES.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        ip, hostname = parts[2], parts[3]
        if ip == pi_static_ip:
            continue
        try:
            if ipaddress.ip_address(ip) not in subnet:
                continue
        except ValueError:
            continue
        host_label = hostname if hostname != "*" else ""
        if is_appliance_host(ip, host_label, pi_static_ip):
            continue
        host = host_label if host_label else f"camera-{ip.replace('.', '-')}"
        found.append(camera_entry(host, ip, onvif=onvif_available(), source="dhcp"))
    return found


def eth0_ipv4() -> Optional[str]:
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", "eth0"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in (out.stdout or "").splitlines():
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    return parts[i + 1].split("/")[0]
    except Exception:
        pass
    return None


def rtsp_port_open(ip: str, port: int = RTSP_PORT, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def discover_rtsp_on_eth0(pi_ip: str, max_workers: int = 48) -> List[Dict[str, Any]]:
    """Customer LAN: hosts on eth0 subnet with RTSP port open."""
    if not pi_ip:
        return []
    try:
        net = ipaddress.ip_network(f"{pi_ip}/24", strict=False)
    except ValueError:
        return []
    hosts = [str(h) for h in net.hosts() if str(h) != pi_ip]
    found: List[Dict[str, Any]] = []

    def check(host: str) -> Optional[Dict[str, Any]]:
        if not rtsp_port_open(host):
            return None
        try:
            hostname = socket.getfqdn(host).split(".")[0]
        except Exception:
            hostname = host
        if hostname == host or not hostname:
            hostname = f"rtsp-{host.replace('.', '-')}"
        return camera_entry(hostname, host, onvif=False, source="rtsp")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(check, h): h for h in hosts}
        for fut in as_completed(futures):
            row = fut.result()
            if row:
                found.append(row)
    return found


def discover_ws(pi_static_ip: str = "192.168.10.1") -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for svc in ws_discover(timeout=8):
        name = svc.get("name", "")
        xaddr = svc.get("xaddr", "")
        ip = ip_from_xaddr(xaddr)
        if not ip or ip in seen or is_appliance_host(ip, name, pi_static_ip):
            continue
        hostname = hostname_for_discovered_camera(ip, name)
        if is_sport_assist_name(name) or is_sport_assist_name(hostname):
            seen.add(ip)
            found.append(
                camera_entry(
                    hostname,
                    ip,
                    onvif=True,
                    source="onvif",
                    onvif_port=port_from_xaddr(xaddr),
                )
            )
    return found


def discover_ws_all(pi_static_ip: str = "192.168.10.1") -> List[Dict[str, Any]]:
    """ONVIF WS-Discovery — any device (customer LAN selection list)."""
    found: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for svc in ws_discover(timeout=8):
        ws_label = svc.get("name", "")
        xaddr = svc.get("xaddr", "")
        ip = ip_from_xaddr(xaddr)
        if not ip or ip in seen or is_appliance_host(ip, ws_label, pi_static_ip):
            continue
        seen.add(ip)
        hostname = hostname_for_discovered_camera(ip, ws_label)
        found.append(
            camera_entry(
                hostname,
                ip,
                onvif=True,
                source="onvif",
                onvif_port=port_from_xaddr(xaddr),
            )
        )
    return found


def discover_getent(pi_static_ip: str = "192.168.10.1") -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    # Hyphenated prefixes only — bare "sport-assist" matches Pi in /etc/hosts (127.0.1.1).
    for prefix in ("SportAssist-", "sport-assist-"):
        try:
            out = subprocess.run(
                ["getent", "hosts", prefix],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in (out.stdout or "").splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    ip, host = parts[0], parts[1]
                    if is_appliance_host(ip, host, pi_static_ip):
                        continue
                    if is_sport_assist_name(host):
                        found.append(camera_entry(host, ip, onvif=onvif_available(), source="dns"))
        except Exception:
            pass
    return found


def merge_cameras(batches: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_ips: Set[str] = set()
    for batch in batches:
        for cam in batch:
            if cam["ip"] not in seen_ips:
                seen_ips.add(cam["ip"])
                out.append(cam)
    return out


def pick_direct_camera(cameras: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not cameras:
        return None
    named = [c for c in cameras if is_sport_assist_name(c.get("hostname", ""))]
    if len(named) == 1:
        return named[0]
    if len(cameras) == 1:
        return cameras[0]
    return named[0] if named else cameras[0]


def direct_eth_status(eth_dhcp: str, pi_static_ip: str = "192.168.10.1") -> Dict[str, Any]:
    """Whether eth0 is on the camera subnet (Direct to Pi)."""
    eth_ip = eth0_ipv4() or ""
    if eth_dhcp != "1":
        return {"mode": "lan", "ethAddress": eth_ip, "cameraNetworkReady": False}
    ready = eth_ip == pi_static_ip
    return {
        "mode": "direct",
        "ethAddress": eth_ip,
        "piStaticIp": pi_static_ip,
        "cameraNetworkReady": ready,
    }


def discover_hint(
    eth_dhcp: str,
    pi_static_ip: str,
    cameras: List[Dict[str, Any]],
) -> Optional[str]:
    if cameras:
        return None
    if eth_dhcp != "1":
        return "No ONVIF/RTSP cameras found on the customer LAN."
    status = direct_eth_status(eth_dhcp, pi_static_ip)
    if not status["cameraNetworkReady"]:
        return (
            "Pi Ethernet is on your home router — normal while the camera is unplugged for SSH. "
            "Connect the camera via PoE injector, then Save Settings (Direct to Pi) to activate camera networking."
        )
    return "No camera DHCP lease yet — check PoE power and Ethernet cable, then Refresh."


def discover_for_mode(eth_dhcp: str, pi_static_ip: str) -> List[Dict[str, Any]]:
    if eth_dhcp == "1":
        leases = discover_dhcp_leases(pi_static_ip)
        if leases:
            return filter_cameras(leases, pi_static_ip)
        return filter_cameras(
            merge_cameras([discover_ws(pi_static_ip), discover_getent(pi_static_ip)]),
            pi_static_ip,
        )
    pi_ip = eth0_ipv4()
    return filter_cameras(
        merge_cameras(
            [
                discover_ws_all(pi_static_ip),
                discover_getent(pi_static_ip),
                discover_rtsp_on_eth0(pi_ip) if pi_ip else [],
            ]
        ),
        pi_static_ip,
    )


def apply_saved_hostnames(cameras: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """When a camera IP is already saved on the Pi, show that hostname (not ONVIF model name)."""
    env = load_env(SPORTASSIST_ETC / "camera.env")
    saved_ip = env.get("CAMERA_IP", "").strip()
    saved_host = env.get("CAMERA_HOSTNAME", "").strip()
    if not saved_ip or not saved_host:
        return cameras
    for cam in cameras:
        if cam.get("ip") == saved_ip:
            discovered = cam.get("hostname", "")
            if discovered and discovered != saved_host:
                cam["discoveredName"] = discovered
            cam["hostname"] = saved_host
    return cameras


def main() -> int:
    try:
        net = load_env(SPORTASSIST_ETC / "network.env")
        eth_dhcp = net.get("ETH_CAMERA_DHCP", "1")
        pi_static = net.get("PI_STATIC_IP", "192.168.10.1")
        cameras = apply_saved_hostnames(discover_for_mode(eth_dhcp, pi_static))
        print(json.dumps(cameras))
        return 0
    except Exception as exc:
        print("[]", flush=True)
        print(f"discover_cameras: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
