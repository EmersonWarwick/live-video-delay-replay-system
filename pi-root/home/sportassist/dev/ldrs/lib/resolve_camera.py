#!/usr/bin/env python3
"""Resolve camera IP — verify saved address or search network by device identifier."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.discover_cameras import discover_for_mode
from lib.env_util import SPORTASSIST_ETC, load_env, update_env_keys
from lib.ffprobe_util import build_rtsp_url, probe_ok
from lib.onvif_client import (
    connect_onvif,
    device_id_from_information,
    get_device_information,
    onvif_available,
)

RUN_IP = Path("/run/sportassist/camera.ip")
PROBE_TIMEOUT_S = 6


def _stream_reachable(env: Dict[str, str], ip: str) -> bool:
    path = env.get("CAMERA_RTSP_PATH", "").strip()
    user = env.get("CAMERA_USERNAME", "").strip()
    password = env.get("CAMERA_PASSWORD", "")
    if not path or not user or not password or not ip:
        return False
    port = int(env.get("CAMERA_RTSP_PORT") or 554)
    url = build_rtsp_url(ip, port, path, user, password)
    return probe_ok(url, min_fps=1, timeout_s=PROBE_TIMEOUT_S)


def _device_id_at_ip(env: Dict[str, str], ip: str) -> Optional[str]:
    if not onvif_available():
        return None
    user = env.get("CAMERA_USERNAME", "").strip()
    password = env.get("CAMERA_PASSWORD", "")
    if not user or not password:
        return None
    onvif_port = int(env.get("CAMERA_ONVIF_PORT") or 80)
    try:
        cam = connect_onvif(ip, user, password, port=onvif_port)
        return device_id_from_information(get_device_information(cam))
    except Exception:
        return None


def _ip_matches_saved_camera(env: Dict[str, str], ip: str) -> bool:
    if not _stream_reachable(env, ip):
        return False
    saved_id = env.get("CAMERA_DEVICE_ID", "").strip()
    if not saved_id:
        return True
    actual = _device_id_at_ip(env, ip)
    if not actual:
        return True
    return actual == saved_id


def _candidate_ips(env: Dict[str, str]) -> List[Dict[str, Any]]:
    net = load_env(SPORTASSIST_ETC / "network.env")
    eth_dhcp = net.get("ETH_CAMERA_DHCP", "1")
    pi_static = net.get("PI_STATIC_IP", "192.168.10.1")
    return discover_for_mode(eth_dhcp, pi_static)


def _find_ip_by_device_id(env: Dict[str, str]) -> Optional[str]:
    saved_id = env.get("CAMERA_DEVICE_ID", "").strip()
    if not saved_id:
        return None
    for cam in _candidate_ips(env):
        ip = cam.get("ip", "")
        if not ip or ip == env.get("CAMERA_IP", "").strip():
            continue
        actual = _device_id_at_ip(env, ip)
        if actual == saved_id and _stream_reachable(env, ip):
            return ip
    return None


def _write_runtime_ip(ip: str) -> None:
    RUN_IP.parent.mkdir(parents=True, exist_ok=True)
    RUN_IP.write_text(ip + "\n", encoding="utf-8")


from lib.buffer_util import (
    hdmi_focus_mode,
    ingest_needs_restart,
    restart_hdmi_service,
    restart_replay_pipeline,
)
from lib.onvif_lens import apply_active_preset


def resolve_camera(*, restart_on_change: bool = True) -> Dict[str, Any]:
    env = load_env(SPORTASSIST_ETC / "camera.env")
    saved_ip = env.get("CAMERA_IP", "").strip()
    assigned = env.get("CAMERA_ASSIGNED") == "1"
    configured = bool(env.get("CAMERA_RTSP_PATH", "").strip())

    if not configured or not env.get("CAMERA_USERNAME") or not env.get("CAMERA_PASSWORD"):
        if saved_ip:
            _write_runtime_ip(saved_ip)
            return {"ok": True, "ip": saved_ip, "changed": False, "reason": "unconfigured"}
        return {"ok": False, "ip": "", "changed": False, "reason": "not_configured"}

    if saved_ip and _ip_matches_saved_camera(env, saved_ip):
        _write_runtime_ip(saved_ip)
        out: Dict[str, Any] = {
            "ok": True,
            "ip": saved_ip,
            "changed": False,
            "reason": "saved_ip_ok",
        }
        return out

    new_ip = _find_ip_by_device_id(env)
    if not new_ip and assigned:
        for cam in _candidate_ips(env):
            ip = cam.get("ip", "")
            if ip and ip != saved_ip and _ip_matches_saved_camera(env, ip):
                new_ip = ip
                break

    if not new_ip:
        if saved_ip:
            _write_runtime_ip(saved_ip)
        out = {
            "ok": False,
            "ip": saved_ip,
            "changed": False,
            "reason": "camera_not_found",
        }
        if restart_on_change and configured and ingest_needs_restart():
            restart_replay_pipeline()
            out["ingestRestart"] = True
        return out

    changed = new_ip != saved_ip
    updates: Dict[str, str] = {"CAMERA_IP": new_ip}
    if assigned:
        actual_id = _device_id_at_ip(env, new_ip)
        if actual_id and not env.get("CAMERA_DEVICE_ID"):
            updates["CAMERA_DEVICE_ID"] = actual_id
    update_env_keys(SPORTASSIST_ETC / "camera.env", updates)
    _write_runtime_ip(new_ip)
    if changed and restart_on_change:
        if hdmi_focus_mode():
            restart_hdmi_service()
        else:
            restart_replay_pipeline()
    try:
        lens_result = apply_active_preset(force=changed)
    except Exception:
        lens_result = {}
    out = {
        "ok": True,
        "ip": new_ip,
        "changed": changed,
        "reason": "relocated" if changed else "found",
    }
    if lens_result:
        out["lensPreset"] = lens_result
    return out


def watch_camera() -> Dict[str, Any]:
    """Periodic watchdog — relocate camera or restart ingest when stream is lost."""
    subprocess.run(
        ["/usr/local/bin/ldrs-camera-discovery.sh"],
        capture_output=True,
        timeout=120,
        check=False,
    )
    result = resolve_camera(restart_on_change=True)
    if not result.get("ingestRestart") and ingest_needs_restart():
        env = load_env(SPORTASSIST_ETC / "camera.env")
        if env.get("CAMERA_RTSP_PATH", "").strip():
            restart_replay_pipeline()
            result["ingestRestart"] = True
            result["reason"] = "ingest_stale"
    return result


def main() -> int:
    try:
        result = watch_camera() if "--watch" in sys.argv else resolve_camera(restart_on_change=True)
        print(json.dumps(result))
        return 0 if result.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "changed": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
