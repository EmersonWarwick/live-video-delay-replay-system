#!/usr/bin/env python3
"""Sport Assist v2 — Flask web, HLS, settings API."""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

LDRS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LDRS_ROOT))

from lib.delay_util import delay_bounds, playback_offset_seconds
from lib.discover_cameras import direct_eth_status, discover_hint, ip_in_camera_subnet
from lib.env_util import load_env  # noqa: E402
from lib.hdmi_resolution_util import format_hdmi_display_mode, read_hdmi_display_mode
from lib.onvif_lens import slugify_preset_id  # noqa: E402
from lib.status_util import build_status, hdmi_focus_mode  # noqa: E402
from lib.delay_playlist_util import playlist_fresh  # noqa: E402
from lib.review_util import build_review  # noqa: E402
from lib.wifi_scrub_playlist import build_hdmi_delay_playlist  # noqa: E402

WEB_ENV = Path("/etc/sportassist/web.env")
SYSTEM_ENV = Path("/etc/sportassist/system.env")
NETWORK_ENV = Path("/etc/sportassist/network.env")
CAMERA_ENV = Path("/etc/sportassist/camera.env")
WIFI_ENV = Path("/etc/sportassist/wifi-ap.env")
WIFI_NETWORK_ENV = Path("/etc/sportassist/wifi-network.env")
LENS_PRESETS = Path("/etc/sportassist/lens-presets.json")
HLS_WIFI = Path("/var/lib/sportassist/hls")
HLS_4K = Path("/var/lib/sportassist/hls-4k")
TEMPLATES = Path(__file__).resolve().parent / "templates"
WEB_DIR = LDRS_ROOT / "web"

DELAY_MAX = 60
DEFAULT_WEB_SESSION_TIMEOUT = 28800  # 8 hours idle — pool-side session
DEFAULT_WEB_USERNAME = "admin"


def _apply_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

mimetypes.add_type("application/vnd.apple.mpegurl", ".m3u8")
mimetypes.add_type("video/mp4", ".m4s")
mimetypes.add_type("video/mp4", ".mp4")


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(TEMPLATES))

    web = load_env(WEB_ENV)
    password = web.get("SETTINGS_PASSWORD", "")
    username = web.get("SETTINGS_USERNAME", DEFAULT_WEB_USERNAME).strip() or DEFAULT_WEB_USERNAME
    if not password:
        app.logger.warning("SETTINGS_PASSWORD not set — web will refuse to start in main()")
    app.secret_key = web.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    app.config["SETTINGS_PASSWORD"] = password
    app.config["SETTINGS_VIEW_PASSWORD"] = web.get("SETTINGS_VIEW_PASSWORD", "")
    app.config["WEB_USERNAME"] = username
    try:
        session_timeout = int(
            web.get("WEB_SESSION_TIMEOUT")
            or web.get("SETTINGS_SESSION_TIMEOUT")
            or str(DEFAULT_WEB_SESSION_TIMEOUT)
        )
    except ValueError:
        session_timeout = DEFAULT_WEB_SESSION_TIMEOUT
    if session_timeout < 60:
        session_timeout = DEFAULT_WEB_SESSION_TIMEOUT
    app.config["WEB_SESSION_TIMEOUT"] = session_timeout

    @app.after_request
    def add_cors_headers(response):
        return _apply_cors_headers(response)

    @app.route("/api/<path:_path>", methods=["OPTIONS"])
    @app.route("/settings/<path:_path>", methods=["OPTIONS"])
    @app.route("/presets/<path:_path>", methods=["OPTIONS"])
    @app.route("/hls/<path:_path>", methods=["OPTIONS"])
    @app.route("/hls-4k/<path:_path>", methods=["OPTIONS"])
    def cors_preflight(_path: str = ""):
        return _apply_cors_headers(app.make_response(("", 204)))

    def web_session_valid(*, touch: bool = True) -> bool:
        if not session.get("web_auth"):
            return False
        timeout = app.config["WEB_SESSION_TIMEOUT"]
        last = session.get("web_last_activity", 0)
        try:
            last_f = float(last)
        except (TypeError, ValueError):
            last_f = 0.0
        now = time.time()
        if now - last_f > timeout:
            session.clear()
            return False
        if touch:
            session["web_last_activity"] = now
            session.modified = True
        return True

    def web_authenticated() -> bool:
        return web_session_valid(touch=False)

    def _touch_session_on_request() -> bool:
        """HLS segment storms must not rewrite the session cookie on every request."""
        path = request.path
        if path.startswith("/hls") or path.startswith("/web/"):
            return False
        if path.endswith((".m4s", ".ts", ".mp4", ".m3u8")):
            return False
        return True

    def start_web_session() -> None:
        session["web_auth"] = True
        session["web_last_activity"] = time.time()
        session.permanent = True
        session.modified = True

    def settings_view_authenticated() -> bool:
        return bool(session.get("settings_view_auth"))

    def start_settings_view_session() -> None:
        session["settings_view_auth"] = True
        session.modified = True

    def settings_view_path_requires_unlock() -> bool:
        path = request.path
        if path in ("/settings/unlock", "/settings/login", "/settings/logout"):
            return False
        if path in ("/settings", "/settings/network"):
            return True
        if path.startswith("/settings/"):
            return True
        if path.startswith("/api/camera"):
            return True
        if path.startswith("/api/network"):
            return True
        return False

    def _settings_unlock_redirect() -> str:
        nxt = (request.args.get("next") or request.form.get("next") or "").strip()
        if nxt and nxt.startswith("/") and not nxt.startswith("//"):
            return nxt
        return url_for("settings_page")

    def _login_redirect_target() -> str:
        nxt = (request.args.get("next") or request.form.get("next") or "").strip()
        if nxt and nxt.startswith("/") and not nxt.startswith("//"):
            return nxt
        return url_for("replay_page")

    PUBLIC_ENDPOINTS = frozenset({"web_login", "cors_preflight", "device_info"})

    @app.before_request
    def enforce_web_auth():
        if request.method == "OPTIONS":
            return None
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if web_session_valid(touch=_touch_session_on_request()):
            return None
        if request.path.startswith("/api/") or request.path.startswith("/hls"):
            return jsonify({"error": "authentication_required"}), 401
        return redirect(url_for("web_login", next=request.path))

    @app.before_request
    def enforce_settings_view():
        if request.method == "OPTIONS":
            return None
        if request.endpoint == "settings_unlock":
            return None
        if not web_session_valid(touch=False):
            return None
        if not app.config.get("SETTINGS_VIEW_PASSWORD"):
            return None
        if not settings_view_path_requires_unlock():
            return None
        if settings_view_authenticated():
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "settings_password_required"}), 403
        return redirect(url_for("settings_unlock", next=request.path))

    @app.route("/")
    def index():
        if web_authenticated():
            return redirect(url_for("replay_page"))
        return redirect(url_for("web_login"))

    @app.route("/login", methods=["GET", "POST"])
    @app.route("/settings/login", methods=["GET", "POST"])
    def web_login():
        if web_authenticated():
            return redirect(_login_redirect_target())
        error = None
        if request.args.get("expired") == "1":
            error = "Session expired — log in again."
        if request.method == "POST":
            expected_user = app.config.get("WEB_USERNAME", DEFAULT_WEB_USERNAME)
            expected_pass = app.config.get("SETTINGS_PASSWORD", "")
            given_user = request.form.get("username", "")
            given_pass = request.form.get("password", "")
            if (
                expected_pass
                and hmac.compare_digest(given_user, expected_user)
                and hmac.compare_digest(given_pass, expected_pass)
            ):
                start_web_session()
                return redirect(_login_redirect_target())
            error = "Incorrect username or password"
            return render_template("login.html", error=error), 401
        return render_template("login.html", error=error)

    @app.route("/settings/unlock", methods=["GET", "POST"])
    def settings_unlock():
        if not web_session_valid(touch=True):
            return redirect(url_for("web_login", next=request.path))
        if settings_view_authenticated():
            return redirect(_settings_unlock_redirect())
        error = None
        next_path = (request.args.get("next") or request.form.get("next") or "").strip()
        if request.method == "POST":
            expected = app.config.get("SETTINGS_VIEW_PASSWORD", "")
            given = request.form.get("password", "")
            if expected and hmac.compare_digest(given, expected):
                start_settings_view_session()
                return redirect(_settings_unlock_redirect())
            error = "Incorrect settings password"
            return render_template(
                "settings_unlock.html", error=error, next_path=next_path
            ), 401
        return render_template("settings_unlock.html", error=error, next_path=next_path)

    @app.post("/logout")
    @app.post("/settings/logout")
    def web_logout():
        session.clear()
        return redirect(url_for("web_login"))

    def read_lens_presets() -> Dict[str, Any]:
        if not LENS_PRESETS.is_file():
            return {"activePresetId": "", "presets": []}
        try:
            return json.loads(LENS_PRESETS.read_text(encoding="utf-8"))
        except Exception:
            return {"activePresetId": "", "presets": []}

    def read_settings_context() -> Dict[str, Any]:
        sys_env = load_env(SYSTEM_ENV)
        net_env = load_env(NETWORK_ENV)
        cam_env = load_env(CAMERA_ENV)
        wifi = load_env(WIFI_ENV)
        wifi_net = load_env(WIFI_NETWORK_ENV)
        device_hostname = wifi_net.get("DEVICE_HOSTNAME", "sport-assist.local")
        eth_dhcp = net_env.get("ETH_CAMERA_DHCP", "1")
        eth_mode = "direct" if eth_dhcp == "1" else "lan"
        hdmi_mode = sys_env.get("HDMI_OUTPUT_MODE", "delayed")
        if hdmi_mode not in ("delayed", "live"):
            hdmi_mode = "delayed"
        hdmi_resolution_mode = sys_env.get("HDMI_RESOLUTION_MODE", "auto")
        if hdmi_resolution_mode not in ("auto", "force_4k"):
            hdmi_resolution_mode = "auto"
        display_mode = read_hdmi_display_mode()
        hdmi_enabled = sys_env.get("HDMI_ENABLED", "1") == "1"
        ssh_enabled = sys_env.get("SSH_ENABLED", "1") == "1"
        idle_rotation = sys_env.get("IDLE_SPLASH_ROTATION", "0")
        if idle_rotation not in ("-90", "0", "90"):
            idle_rotation = "0"
        camera_assigned = cam_env.get("CAMERA_ASSIGNED") == "1" or (
            cam_env.get("CAMERA_USERNAME") == "sportassist"
            and bool(cam_env.get("CAMERA_RTSP_PATH"))
        )
        delay_min, delay_max = delay_bounds(sys_env)
        return {
            "delay": sys_env.get("LIVE_DELAY_SECONDS", "14"),
            "delay_min": delay_min,
            "delay_max": delay_max,
            "pipeline_latency": delay_min,
            "hdmi_mode": hdmi_mode,
            "hdmi_enabled": hdmi_enabled,
            "hdmi_resolution_mode": hdmi_resolution_mode,
            "hdmi_display_resolution": format_hdmi_display_mode(display_mode),
            "ssh_enabled": ssh_enabled,
            "idle_splash_rotation": idle_rotation,
            "eth_mode": eth_mode,
            "ap_ssid": wifi.get("AP_SSID", ""),
            "device_hostname": device_hostname,
            "camera_hostname": cam_env.get("CAMERA_HOSTNAME", ""),
            "camera_ip": cam_env.get("CAMERA_IP", ""),
            "camera_username": cam_env.get("CAMERA_USERNAME", ""),
            "camera_password": cam_env.get("CAMERA_PASSWORD", "") if camera_assigned else "",
            "camera_device_id": cam_env.get("CAMERA_DEVICE_ID", ""),
            "camera_reported_name": cam_env.get("CAMERA_REPORTED_NAME", ""),
            "camera_assigned": camera_assigned,
            "ingest_codec": cam_env.get("INGEST_CODEC", ""),
            "ingest_size": (
                f"{cam_env.get('INGEST_WIDTH', '')}×{cam_env.get('INGEST_HEIGHT', '')}"
                if cam_env.get("INGEST_WIDTH")
                else ""
            ),
            "ingest_fps": cam_env.get("INGEST_FPS", ""),
            "fallback_step": cam_env.get("INGEST_FALLBACK_STEP", ""),
            "status": build_status(),
            "lens_presets": read_lens_presets().get("presets", []),
            "active_preset_id": read_lens_presets().get("activePresetId", ""),
        }

    @app.route("/settings", methods=["GET", "POST"])
    def settings_page():
        errors: List[str] = []
        if request.method == "POST":
            delay_raw = request.form.get("delay", "").strip()
            eth_mode = request.form.get("eth_mode", "").strip()
            idle_rotation = request.form.get("idle_splash_rotation", "").strip()
            if delay_raw:
                try:
                    delay_val = int(delay_raw)
                    delay_min, delay_max = delay_bounds(load_env(SYSTEM_ENV))
                    if delay_val < delay_min or delay_val > delay_max:
                        errors.append(
                            f"Delay must be {delay_min}–{delay_max} seconds "
                            f"(minimum is ingest pipeline latency)."
                        )
                    else:
                        subprocess.run(
                            ["sudo", "/usr/local/bin/ldrs-set-delay.sh", str(delay_val)],
                            check=True,
                        )
                except (ValueError, subprocess.CalledProcessError):
                    errors.append("Failed to update live delay.")
            if eth_mode in ("direct", "lan"):
                mode_arg = "enable" if eth_mode == "direct" else "disable"
                current = read_settings_context()["eth_mode"]
                if eth_mode != current:
                    try:
                        subprocess.run(
                            ["sudo", "/usr/local/bin/ldrs-set-eth-camera-dhcp.sh", mode_arg],
                            check=True,
                        )
                    except subprocess.CalledProcessError:
                        errors.append("Failed to update Ethernet mode.")
            if idle_rotation in ("-90", "0", "90"):
                current = read_settings_context()["idle_splash_rotation"]
                if idle_rotation != current:
                    try:
                        subprocess.run(
                            [
                                "sudo",
                                "/usr/local/bin/ldrs-set-idle-splash-rotation.sh",
                                idle_rotation,
                            ],
                            check=True,
                        )
                    except subprocess.CalledProcessError:
                        errors.append("Failed to update idle screen rotation.")
        ctx = read_settings_context()
        ctx["errors"] = errors
        return render_template("settings.html", **ctx)

    @app.post("/settings/hdmi/enabled")
    def settings_hdmi_enabled():
        data = request.get_json(force=True, silent=True) or {}
        enabled = data.get("enabled")
        if enabled not in (True, False, 0, 1, "0", "1"):
            return jsonify({"ok": False, "error": "invalid_enabled"}), 400
        flag = "1" if enabled in (True, 1, "1") else "0"
        ctx = read_settings_context()
        if (ctx["hdmi_enabled"] and flag == "1") or (not ctx["hdmi_enabled"] and flag == "0"):
            return jsonify({"ok": True, "enabled": flag == "1"})
        try:
            subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-set-hdmi-enabled.sh", flag],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return jsonify({"ok": True, "enabled": flag == "1"})
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or "").strip() or "hdmi_enabled_failed"
            return jsonify({"ok": False, "error": err}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "hdmi_enabled_timeout"}), 504

    @app.post("/settings/ssh/enabled")
    def settings_ssh_enabled():
        data = request.get_json(force=True, silent=True) or {}
        enabled = data.get("enabled")
        if enabled not in (True, False, 0, 1, "0", "1"):
            return jsonify({"ok": False, "error": "invalid_enabled"}), 400
        flag = "1" if enabled in (True, 1, "1") else "0"
        ctx = read_settings_context()
        if (ctx["ssh_enabled"] and flag == "1") or (not ctx["ssh_enabled"] and flag == "0"):
            return jsonify({"ok": True, "enabled": flag == "1"})
        try:
            subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-set-ssh-enabled.sh", flag],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return jsonify({"ok": True, "enabled": flag == "1"})
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or "").strip() or "ssh_enabled_failed"
            return jsonify({"ok": False, "error": err}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "ssh_enabled_timeout"}), 504

    @app.post("/settings/hostname")
    def settings_hostname():
        data = request.get_json(force=True, silent=True) or {}
        hostname = (data.get("hostname") or "").strip()
        if not hostname:
            return jsonify({"ok": False, "error": "hostname_required"}), 400
        body, code = network_cmd("set-hostname", {"hostname": hostname})
        return jsonify(body), code

    @app.post("/settings/hdmi/mode")
    def settings_hdmi_mode():
        data = request.get_json(force=True, silent=True) or {}
        mode = (data.get("mode") or "").strip()
        if mode not in ("delayed", "live"):
            return jsonify({"ok": False, "error": "invalid_mode"}), 400
        try:
            subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-set-hdmi-mode.sh", mode],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            return jsonify({"ok": True, "mode": mode})
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or "").strip() or "hdmi_mode_failed"
            return jsonify({"ok": False, "error": err}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "hdmi_mode_timeout"}), 504

    @app.post("/settings/hdmi/resolution")
    def settings_hdmi_resolution():
        data = request.get_json(force=True, silent=True) or {}
        mode = (data.get("mode") or "").strip()
        if mode not in ("auto", "force_4k"):
            return jsonify({"ok": False, "error": "invalid_mode"}), 400
        ctx = read_settings_context()
        if ctx["hdmi_resolution_mode"] == mode:
            return jsonify(
                {
                    "ok": True,
                    "mode": mode,
                    "display": ctx["hdmi_display_resolution"],
                    "reboot_recommended": False,
                }
            )
        try:
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-set-hdmi-resolution.sh", mode],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            out = (proc.stdout or "").strip()
            reboot_recommended = "runtime_applied=0" in out
            display_mode = read_hdmi_display_mode()
            return jsonify(
                {
                    "ok": True,
                    "mode": mode,
                    "display": format_hdmi_display_mode(display_mode),
                    "reboot_recommended": reboot_recommended,
                }
            )
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or "").strip() or "hdmi_resolution_failed"
            return jsonify({"ok": False, "error": err}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "hdmi_resolution_timeout"}), 504

    def network_cmd(command: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], int]:
        """Run privileged network CLI via sudo."""
        args = ["sudo", "/usr/local/bin/ldrs-wifi-network-cli.sh", command]
        if payload is not None:
            args.append(json.dumps(payload))
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            raw = (proc.stdout or "").strip()
            if not raw:
                err = (proc.stderr or "").strip() or "empty_response"
                return {"ok": False, "error": err}, 500
            body = json.loads(raw)
            code = 200 if body.get("ok", proc.returncode == 0) else 400
            if proc.returncode != 0 and body.get("ok") is not False:
                body = {"ok": False, "error": (proc.stderr or "").strip() or "network_command_failed"}
                code = 500
            return body, code
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "network_command_timeout"}, 504
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid_network_response"}, 500

    @app.get("/settings/network")
    def network_settings_page():
        return render_template("network_settings.html")

    @app.get("/api/network/status")
    def api_network_status():
        body, code = network_cmd("status")
        return jsonify(body), code

    @app.get("/api/network/config")
    def api_network_config():
        body, code = network_cmd("config")
        return jsonify(body), code

    @app.post("/api/network/scan")
    def api_network_scan():
        body, code = network_cmd("scan")
        return jsonify(body), code

    @app.post("/api/network/save")
    def api_network_save():
        data = request.get_json(force=True, silent=True) or {}
        body, code = network_cmd("save", data)
        return jsonify(body), code

    @app.post("/api/network/apply")
    def api_network_apply():
        body, code = network_cmd("apply")
        return jsonify(body), code

    @app.post("/api/network/switch-ap")
    def api_network_switch_ap():
        body, code = network_cmd("switch-ap")
        return jsonify(body), code

    @app.post("/api/network/switch-client")
    def api_network_switch_client():
        body, code = network_cmd("switch-client")
        return jsonify(body), code

    @app.post("/api/network/forget")
    def api_network_forget():
        body, code = network_cmd("forget")
        return jsonify(body), code

    @app.get("/api/network/logs")
    def api_network_logs():
        body, code = network_cmd("logs")
        return jsonify(body), code

    @app.route("/device-info", methods=["GET", "OPTIONS"])
    def device_info():
        if request.method == "OPTIONS":
            return _apply_cors_headers(app.make_response(("", 204)))
        return jsonify({"device": "LDRS2", "status": "OK"})

    @app.get("/api/status")
    def api_status():
        return jsonify(build_status())

    @app.get("/api/review")
    def api_review():
        return jsonify(build_review())

    def ensure_wifi_delayed_playlist() -> bool:
        """Build delayed_sync.m3u8 if missing or still on the old short-window format."""
        source = HLS_WIFI / "live.m3u8"
        sync = HLS_WIFI / "delayed_sync.m3u8"
        if not source.is_file():
            return False
        needs_build = True
        if sync.is_file() and playlist_fresh(sync):
            try:
                text = sync.read_text(encoding="utf-8", errors="replace")
                # Sliding trimmed playlist (~delay window) — not legacy EVENT + full buffer.
                if (
                    "#EXT-X-PLAYLIST-TYPE:EVENT" not in text
                    and 3 < text.count("#EXTINF") < 120
                ):
                    needs_build = False
            except OSError:
                pass
        if needs_build:
            offset = playback_offset_seconds(load_env(SYSTEM_ENV))
            if not build_hdmi_delay_playlist(source, sync, float(offset)):
                return False
        return sync.is_file()

    def hls_send(directory: Path, filename: str):
        if not directory.is_dir():
            abort(404)
        return send_from_directory(directory, filename)

    @app.get("/hls/<path:filename>")
    def hls_wifi(filename: str):
        # Full rolling buffer (20 min scrub) — not delayed.
        if filename == "buffer.m3u8":
            return hls_send(HLS_WIFI, "live.m3u8")
        # Delayed 1080p — full buffer, #EXT-X-START at delay edge (matches HDMI timing).
        if filename == "live.m3u8":
            if not hdmi_focus_mode() and ensure_wifi_delayed_playlist():
                sync = HLS_WIFI / "delayed_sync.m3u8"
                if playlist_fresh(sync):
                    return send_from_directory(HLS_WIFI, "delayed_sync.m3u8")
            return hls_send(HLS_WIFI, "live.m3u8")
        if filename in ("sync.m3u8", "delayed.m3u8"):
            if ensure_wifi_delayed_playlist():
                sync = HLS_WIFI / "delayed_sync.m3u8"
                if playlist_fresh(sync):
                    return send_from_directory(HLS_WIFI, "delayed_sync.m3u8")
        return hls_send(HLS_WIFI, filename)

    @app.get("/hls-4k/<path:filename>")
    def hls_4k(filename: str):
        resp = hls_send(HLS_4K, filename)
        if filename.endswith(".m3u8"):
            resp.headers["Cache-Control"] = "no-cache, no-store"
        return resp

    @app.post("/api/camera/discover")
    def api_camera_discover():
        try:
            net = load_env(NETWORK_ENV)
            eth_dhcp = net.get("ETH_CAMERA_DHCP", "1")
            if eth_dhcp == "1":
                subprocess.run(
                    ["sudo", "/usr/local/bin/ldrs-ensure-camera-network.sh"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                time.sleep(1)
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-discover-cameras.sh"],
                capture_output=True,
                text=True,
                timeout=35,
                check=False,
            )
            raw = (proc.stdout or "").strip()
            try:
                cameras = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                cameras = []
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or f"discover exited {proc.returncode}"
                return jsonify({"searching": False, "cameras": cameras, "error": err})
            if not isinstance(cameras, list):
                cameras = []
            pi_static = net.get("PI_STATIC_IP", "192.168.10.1")
            eth_status = direct_eth_status(eth_dhcp, pi_static)
            hint = discover_hint(eth_dhcp, pi_static, cameras)
            if cameras and eth_dhcp == "1":
                subprocess.run(
                    ["sudo", "/usr/local/bin/ldrs-apply-direct-discovery.sh"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            return jsonify(
                {
                    "searching": False,
                    "cameras": cameras,
                    "error": None,
                    "hint": hint,
                    "ethStatus": eth_status,
                }
            )
        except Exception as exc:
            return jsonify({"searching": False, "cameras": [], "error": str(exc)})

    @app.get("/api/camera")
    def api_camera_get():
        cam = load_env(CAMERA_ENV)
        sub = None
        if cam.get("CAMERA_RTSP_PATH_SUB"):
            sub = {
                "rtspPath": cam.get("CAMERA_RTSP_PATH_SUB"),
                "width": int(cam.get("INGEST_SUB_WIDTH") or 0),
                "height": int(cam.get("INGEST_SUB_HEIGHT") or 0),
                "fps": int(cam.get("INGEST_SUB_FPS") or 0),
                "codec": cam.get("INGEST_SUB_CODEC"),
                "gop": int(cam.get("INGEST_SUB_GOP") or 25),
            }
        return jsonify(
            {
                "hostname": cam.get("CAMERA_HOSTNAME", ""),
                "deviceId": cam.get("CAMERA_DEVICE_ID", ""),
                "reportedName": cam.get("CAMERA_REPORTED_NAME", ""),
                "ip": cam.get("CAMERA_IP", ""),
                "username": cam.get("CAMERA_USERNAME", ""),
                "rtspPort": int(cam.get("CAMERA_RTSP_PORT") or 554),
                "rtspPath": cam.get("CAMERA_RTSP_PATH", ""),
                "ingestWidth": int(cam.get("INGEST_WIDTH") or 0) or None,
                "ingestHeight": int(cam.get("INGEST_HEIGHT") or 0) or None,
                "ingestFps": int(cam.get("INGEST_FPS") or 0) or None,
                "ingestCodec": cam.get("INGEST_CODEC", ""),
                "ingestGop": int(cam.get("INGEST_GOP") or 25),
                "ingestBitrate": int(cam.get("INGEST_BITRATE") or 0) or None,
                "fallbackStep": int(cam.get("INGEST_FALLBACK_STEP") or 0) or None,
                "streamLabel": cam.get("CAMERA_STREAM_LABEL", ""),
                "subStream": sub,
                "configured": bool(cam.get("CAMERA_RTSP_PATH")),
            }
        )

    @app.post("/api/camera/test")
    def api_camera_test():
        data = request.get_json(force=True, silent=True) or {}
        ip = data.get("ip", "")
        username = data.get("currentUsername") or data.get("username", "")
        password = data.get("currentPassword") or data.get("password", "")
        onvif_port = str(data.get("onvifPort") or 80)
        if not all([ip, username, password]):
            return jsonify({"ok": False, "error": "missing_fields"}), 400
        net = load_env(NETWORK_ENV)
        if net.get("ETH_CAMERA_DHCP", "1") == "1":
            pi_static = net.get("PI_STATIC_IP", "192.168.10.1")
            if not ip_in_camera_subnet(ip, pi_static):
                prefix = pi_static.rsplit(".", 1)[0]
                return jsonify(
                    {
                        "ok": False,
                        "error": "wrong_subnet",
                        "hint": f"Direct to Pi mode expects a camera on {prefix}.x (PoE Ethernet). Refresh camera after connecting.",
                    }
                ), 400
        try:
            proc = subprocess.run(
                [
                    "sudo",
                    "/usr/local/bin/ldrs-test-camera-auth.sh",
                    ip,
                    username,
                    password,
                    onvif_port,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            body = json.loads(proc.stdout or "{}")
            if proc.returncode != 0:
                return jsonify(body), 400
            return jsonify(body)
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "onvif_unreachable"}), 504
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/camera/assign")
    def api_camera_assign():
        data = request.get_json(force=True, silent=True) or {}
        ip = (data.get("ip") or "").strip()
        current_user = (data.get("currentUsername") or data.get("username") or "").strip()
        current_pass = data.get("currentPassword") or data.get("password") or ""
        if not all([ip, current_user, current_pass]):
            return jsonify({"ok": False, "error": "missing_fields"}), 400
        net = load_env(NETWORK_ENV)
        if net.get("ETH_CAMERA_DHCP", "1") == "1":
            pi_static = net.get("PI_STATIC_IP", "192.168.10.1")
            if not ip_in_camera_subnet(ip, pi_static):
                prefix = pi_static.rsplit(".", 1)[0]
                return jsonify(
                    {
                        "ok": False,
                        "error": "wrong_subnet",
                        "hint": f"Direct to Pi mode expects a camera on {prefix}.x (PoE Ethernet). Refresh camera after connecting.",
                    }
                ), 400
        payload = {
            "ip": ip,
            "currentUsername": current_user,
            "currentPassword": current_pass,
            "rtspPort": int(data.get("rtspPort") or 554),
            "onvifPort": int(data.get("onvifPort") or 80),
        }
        try:
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-assign-camera.sh"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            body = json.loads(proc.stdout or "{}")
            if proc.returncode != 0:
                return jsonify({"ok": False, **body}), 400
            return jsonify({"ok": True, "cameraConnected": body.get("configured", True), **body})
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "configure_timeout"}), 504
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/camera/clear")
    def api_camera_clear():
        try:
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-clear-camera-config.sh"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip() or "clear failed"
                return jsonify({"ok": False, "error": err}), 400
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/camera")
    def api_camera_post():
        data = request.get_json(force=True, silent=True) or {}
        hostname = data.get("hostname", "")
        ip = data.get("ip", "")
        username = data.get("username", "")
        password = data.get("password", "")
        port = str(data.get("rtspPort", 554))
        onvif_port = str(data.get("onvifPort") or 80)
        if not all([hostname, ip, username, password]):
            return jsonify({"ok": False, "error": "missing_fields"}), 400
        try:
            proc = subprocess.run(
                [
                    "sudo",
                    "/usr/local/bin/ldrs-set-camera-config.sh",
                    hostname,
                    ip,
                    username,
                    password,
                    port,
                    onvif_port,
                ],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            body = json.loads(proc.stdout or "{}")
            if proc.returncode != 0:
                return jsonify({"ok": False, **body}), 400
            return jsonify({"ok": True, "cameraConnected": body.get("configured", True), **body})
        except subprocess.TimeoutExpired:
            return jsonify({"ok": False, "error": "configure_timeout"}), 504
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/camera/streams")
    def api_camera_streams():
        data = request.get_json(force=True, silent=True) or {}
        try:
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-configure-camera-streams.sh"],
                input=json.dumps(data),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            body = json.loads(proc.stdout or "{}")
            if proc.returncode != 0:
                return jsonify(body), 400
            return jsonify(body)
        except subprocess.TimeoutExpired:
            return jsonify({"configured": False, "error": "configure_timeout"}), 504
        except Exception as exc:
            return jsonify({"configured": False, "error": str(exc)}), 500

    def lens_cmd(args: List[str], timeout: int = 50) -> Tuple[dict, int]:
        try:
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-onvif-lens.sh", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            body = json.loads(proc.stdout or "{}")
            return body, proc.returncode
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "lens_timeout"}, 504
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500

    def osd_cmd(args: List[str], timeout: int = 15) -> Tuple[dict, int]:
        try:
            proc = subprocess.run(
                ["sudo", "/usr/local/bin/ldrs-onvif-osd.sh", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            body = json.loads(proc.stdout or "{}")
            return body, proc.returncode
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500

    @app.get("/settings/lens/position")
    def lens_position_get():
        body, code = lens_cmd(["state"])
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/position")
    def lens_position_set():
        data = request.get_json(force=True, silent=True) or request.form
        args = ["set-position"]
        if "zoom" in data and data.get("zoom") is not None:
            args.append(str(data["zoom"]))
        else:
            args.append("-")
        if "focus" in data and data.get("focus") is not None:
            args.append(str(data["focus"]))
        else:
            args.append("-")
        if args[1] == "-" and args[2] == "-":
            return jsonify({"ok": False, "error": "zoom_or_focus_required"}), 400
        body, code = lens_cmd(args)
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/move")
    def lens_move():
        axis = request.json.get("axis", "zoom") if request.is_json else request.form.get("axis", "zoom")
        direction = request.json.get("direction", "in") if request.is_json else request.form.get("direction", "in")
        body, code = lens_cmd(["move", axis, direction])
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/stop")
    def lens_stop():
        body, code = lens_cmd(["stop"])
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/autofocus")
    def lens_autofocus():
        data = request.get_json(force=True, silent=True) or request.form
        if data.get("enabled") is not None:
            enabled = str(data.get("enabled")).lower() in ("1", "true", "on", "yes")
            body, code = lens_cmd(["set-autofocus", "on" if enabled else "off"])
            return jsonify(body), (200 if code == 0 else 400)
        body, code = lens_cmd(["autofocus"])
        return jsonify(body), (200 if code == 0 else 400)

    @app.get("/settings/camera/datestamp")
    def camera_datestamp_get():
        body, code = osd_cmd(["state"])
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/camera/datestamp")
    def camera_datestamp_set():
        data = request.get_json(force=True, silent=True) or request.form
        enabled = str(data.get("enabled", "")).lower() in ("1", "true", "on", "yes")
        body, code = osd_cmd(["on" if enabled else "off"])
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/preset/save")
    def lens_preset_save():
        data = request.get_json(force=True, silent=True) or request.form
        pid = (data.get("id") or "").strip()
        label = (data.get("label") or "").strip()
        presets_data = read_lens_presets()
        existing = {p.get("id") for p in presets_data.get("presets", []) if p.get("id")}
        if not pid:
            if not label:
                return jsonify({"ok": False, "error": "label_required"}), 400
            pid = slugify_preset_id(label, existing)
        if not label:
            preset = next(
                (p for p in presets_data.get("presets", []) if p.get("id") == pid),
                None,
            )
            label = (preset or {}).get("label") or pid
        args = ["preset", "save-onvif", pid, label]
        body, code = lens_cmd(args, timeout=50)
        return jsonify(body), (200 if code == 0 else 400)

    @app.get("/settings/lens/preset/list-onvif")
    def lens_preset_list_onvif():
        body, code = lens_cmd(["preset", "list-onvif"], timeout=30)
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/preset/recall")
    def lens_preset_recall():
        data = request.get_json(force=True, silent=True) or request.form
        pid = data.get("id", "wide")
        body, code = lens_cmd(["preset", "recall", pid], timeout=50)
        return jsonify(body), (200 if code == 0 else 400)

    @app.post("/settings/lens/preset/delete")
    def lens_preset_delete():
        data = request.get_json(force=True, silent=True) or request.form
        pid = data.get("id", "")
        body, code = lens_cmd(["preset", "delete", pid])
        return jsonify(body), (200 if code == 0 else 400)

    @app.get("/replay")
    def replay_page():
        return render_template("replay.html")

    @app.get("/review")
    def review_redirect():
        return redirect(url_for("replay_page"), code=302)

    @app.get("/presets")
    def presets_page():
        presets_data = read_lens_presets()
        return render_template(
            "presets.html",
            presets=presets_data.get("presets", []),
            active_preset_id=presets_data.get("activePresetId", ""),
        )

    @app.post("/presets/recall")
    def presets_recall():
        data = request.get_json(force=True, silent=True) or request.form
        pid = (data.get("id") or "").strip()
        if not pid:
            return jsonify({"ok": False, "error": "preset_id_required"}), 400
        body, code = lens_cmd(["preset", "recall", pid], timeout=50)
        return jsonify(body), (200 if code == 0 else 400)

    @app.get("/web/<path:filename>")
    def web_static(filename: str):
        path = WEB_DIR / filename
        if path.is_file():
            return send_from_directory(WEB_DIR, filename)
        abort(404)

    return app


def main() -> None:
    app = create_app()
    if not app.config.get("SETTINGS_PASSWORD"):
        raise SystemExit(f"Refusing to start: set SETTINGS_PASSWORD in {WEB_ENV}")
    port = int(os.environ.get("LDRS_WEB_PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
