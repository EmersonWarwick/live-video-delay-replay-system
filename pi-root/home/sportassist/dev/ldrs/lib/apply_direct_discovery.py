#!/usr/bin/env python3
"""Direct mode: write discovered camera IP into camera.env (hostname only before assign)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.discover_cameras import (
    discover_dhcp_leases,
    ip_in_camera_subnet,
    pick_direct_camera,
)
from lib.env_util import SPORTASSIST_ETC, load_env, update_env_keys

RUN_IP = Path("/run/sportassist/camera.ip")


def main() -> int:
    net = load_env(SPORTASSIST_ETC / "network.env")
    if net.get("ETH_CAMERA_DHCP", "1") != "1":
        return 0

    cam_env = load_env(SPORTASSIST_ETC / "camera.env")
    assigned = cam_env.get("CAMERA_ASSIGNED") == "1"

    pi_static = net.get("PI_STATIC_IP", "192.168.10.1")
    current_ip = cam_env.get("CAMERA_IP", "").strip()
    if current_ip and not ip_in_camera_subnet(current_ip, pi_static):
        updates = {"CAMERA_IP": ""}
        if not assigned:
            updates["CAMERA_HOSTNAME"] = ""
        update_env_keys(SPORTASSIST_ETC / "camera.env", updates)
        if RUN_IP.is_file():
            RUN_IP.unlink(missing_ok=True)

    cameras = discover_dhcp_leases(pi_static)
    if not cameras:
        return 0

    chosen = pick_direct_camera(cameras)
    if not chosen:
        return 0

    ip = chosen["ip"]
    updates: dict[str, str] = {"CAMERA_IP": ip}
    if not assigned:
        updates["CAMERA_HOSTNAME"] = chosen["hostname"]

    update_env_keys(SPORTASSIST_ETC / "camera.env", updates)
    RUN_IP.parent.mkdir(parents=True, exist_ok=True)
    RUN_IP.write_text(ip + "\n", encoding="utf-8")
    label = cam_env.get("CAMERA_HOSTNAME") or chosen["hostname"]
    print(f"Direct discovery: {label} @ {ip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
