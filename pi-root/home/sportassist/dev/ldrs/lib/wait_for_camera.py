#!/usr/bin/env python3
"""Wait until camera Ethernet is up and RTSP ingest is reachable (boot / cold start)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.env_util import SPORTASSIST_ETC, load_env
from lib.ffprobe_util import build_rtsp_url, probe_ok

RUN_IP = Path("/run/sportassist/camera.ip")
DEFAULT_MAX_WAIT_S = 300
POLL_S = 5
PROBE_TIMEOUT_S = 8


def _eth0_has_pi_ip() -> bool:
    net = load_env(SPORTASSIST_ETC / "network.env")
    if net.get("ETH_CAMERA_DHCP", "1") != "1":
        return True
    pi_ip = net.get("PI_STATIC_IP", "192.168.10.1")
    iface = net.get("PI_INTERFACE", "eth0")
    try:
        proc = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", iface],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return pi_ip in (proc.stdout or "")
    except (subprocess.TimeoutExpired, OSError):
        return False


def _ensure_camera_network() -> None:
    if _eth0_has_pi_ip():
        return
    subprocess.run(
        ["/usr/local/bin/ldrs-network.sh"],
        check=False,
        timeout=60,
    )


def _camera_ip(env: dict[str, str]) -> str:
    if RUN_IP.is_file():
        ip = RUN_IP.read_text(encoding="utf-8").strip()
        if ip:
            return ip
    return env.get("CAMERA_IP", "").strip()


def _stream_ready(env: dict[str, str], ip: str) -> bool:
    path = env.get("CAMERA_RTSP_PATH", "").strip()
    user = env.get("CAMERA_USERNAME", "").strip()
    password = env.get("CAMERA_PASSWORD", "")
    if not ip or not path or not user or not password:
        return False
    port = int(env.get("CAMERA_RTSP_PORT") or 554)
    url = build_rtsp_url(ip, port, path, user, password)
    return probe_ok(url, min_fps=1, timeout_s=PROBE_TIMEOUT_S)


def wait_for_camera(max_wait_s: int = DEFAULT_MAX_WAIT_S) -> dict[str, object]:
    env = load_env(SPORTASSIST_ETC / "camera.env")
    if not env.get("CAMERA_RTSP_PATH", "").strip():
        return {"ok": False, "reason": "not_configured"}

    deadline = time.monotonic() + max_wait_s
    started = time.monotonic()
    last_ip = ""
    while time.monotonic() < deadline:
        _ensure_camera_network()
        subprocess.run(
            ["/usr/local/bin/ldrs-camera-discovery.sh"],
            check=False,
            timeout=120,
        )
        ip = _camera_ip(env)
        if ip:
            last_ip = ip
        if ip and _stream_ready(env, ip):
            RUN_IP.parent.mkdir(parents=True, exist_ok=True)
            RUN_IP.write_text(ip + "\n", encoding="utf-8")
            return {"ok": True, "ip": ip, "waited_s": round(time.monotonic() - started)}
        time.sleep(POLL_S)

    return {"ok": False, "reason": "timeout", "ip": last_ip, "max_wait_s": max_wait_s}


def main() -> int:
    max_wait = DEFAULT_MAX_WAIT_S
    if len(sys.argv) > 1:
        try:
            max_wait = int(sys.argv[1])
        except ValueError:
            pass
    result = wait_for_camera(max_wait_s=max_wait)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
