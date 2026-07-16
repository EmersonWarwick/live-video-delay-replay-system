#!/usr/bin/env python3
"""ONVIF lens move / stop / autofocus / presets."""
from __future__ import annotations

import json
import re
import sys
import time
import fcntl
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.env_util import SPORTASSIST_ETC, load_env
from lib.onvif_client import connect_onvif, onvif_available

PRESETS_PATH = SPORTASSIST_ETC / "lens-presets.json"
LENS_APPLIED_MARKER = Path("/run/sportassist/lens-preset-applied")
MIN_PRESETS = 0
MAX_PRESETS = 8
# Normalised position change per button click (0.0–1.0 scale).
ZOOM_STEP = 0.025
FOCUS_STEP = 0.02
FOCUS_MOVE_SPEED = 0.2
ZOOM_SETTLE_S = 0.8
ZOOM_MOVE_TIMEOUT_S = 10.0
GOTO_PRESET_SETTLE_S = 1.5
FOCUS_HOLD_S = 1.0
MOVE_SPEED = 0.3
PRESET_TOLERANCE = 0.03
LENS_LOCK_PATH = Path("/run/sportassist/lens.lock")
_IMAGING_VS_TOKEN: Optional[str] = None
_ONVIF_PRESETS_SUPPORTED: Optional[bool] = None
_lens_lock_fd: Optional[Any] = None


def load_presets() -> Dict[str, Any]:
    if not PRESETS_PATH.is_file():
        return {"activePresetId": "wide", "presets": []}
    return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))


def save_presets(data: Dict[str, Any]) -> None:
    PRESETS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def find_preset(data: Dict[str, Any], preset_id: str) -> Optional[Dict[str, Any]]:
    for preset in data.get("presets", []):
        if preset.get("id") == preset_id:
            return preset
    return None


def slugify_preset_id(label: str, existing_ids: Set[str]) -> str:
    """Derive a stable machine id from a user-visible label."""
    base = re.sub(r"[^a-z0-9]+", "-", label.lower().strip()).strip("-")[:32]
    if not base:
        base = "preset"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        tail = f"-{suffix}"
        candidate = f"{base[: 32 - len(tail)]}{tail}"
        suffix += 1
    return candidate


def camera_from_env():
    env = load_env(SPORTASSIST_ETC / "camera.env")
    ip = env.get("CAMERA_IP", "").strip()
    user = env.get("CAMERA_USERNAME", "").strip()
    password = env.get("CAMERA_PASSWORD", "")
    onvif_port = int(env.get("CAMERA_ONVIF_PORT") or 80)
    if not ip or not user:
        raise RuntimeError("camera_not_configured")
    return connect_onvif(ip, user, password, port=onvif_port)


def _primary_profile(cam):
    profiles = cam.create_media_service().GetProfiles()
    if not profiles:
        raise RuntimeError("no_onvif_profiles")
    return profiles[0]


def _profile_token(cam) -> str:
    return _primary_profile(cam).token


def _video_source_token(cam) -> str:
    tokens = _iter_video_source_tokens(cam)
    return tokens[0]


def _discover_video_source_tokens(cam) -> list[str]:
    """All known video source tokens (profile SourceToken + GetVideoSources)."""
    seen: set[str] = set()
    ordered: list[str] = []
    try:
        vs = _primary_profile(cam).VideoSourceConfiguration
        token = getattr(vs, "SourceToken", None) if vs else None
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    except Exception:
        pass
    try:
        for src in cam.create_media_service().GetVideoSources():
            token = getattr(src, "token", None)
            if token and token not in seen:
                seen.add(token)
                ordered.append(token)
    except Exception:
        pass
    if not ordered:
        raise RuntimeError("no_video_source")
    return ordered


def _iter_video_source_tokens(cam) -> list[str]:
    """Try cached imaging token first, then every other discovered token."""
    global _IMAGING_VS_TOKEN
    tokens = _discover_video_source_tokens(cam)
    if _IMAGING_VS_TOKEN and _IMAGING_VS_TOKEN in tokens:
        return [_IMAGING_VS_TOKEN] + [t for t in tokens if t != _IMAGING_VS_TOKEN]
    if not _IMAGING_VS_TOKEN:
        _IMAGING_VS_TOKEN = tokens[0]
    return tokens


def _acquire_lens_lock() -> None:
    global _lens_lock_fd
    LENS_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = open(LENS_LOCK_PATH, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        raise RuntimeError("lens_busy")
    _lens_lock_fd = fd


def _release_lens_lock() -> None:
    global _lens_lock_fd
    if _lens_lock_fd is None:
        return
    try:
        fcntl.flock(_lens_lock_fd.fileno(), fcntl.LOCK_UN)
        _lens_lock_fd.close()
    except Exception:
        pass
    _lens_lock_fd = None


def _ptz_service(cam):
    return cam.create_ptz_service()


def _imaging_service(cam):
    return cam.create_imaging_service()


def read_autofocus_state(cam) -> bool:
    """Read auto-focus mode from the camera (source of truth for UI)."""
    return is_autofocus_enabled(cam)


def report_autofocus_state(cam, *, requested: Optional[bool] = None) -> bool:
    """Return camera-reported AF; fall back to requested when read is ambiguous."""
    reported = is_autofocus_enabled(cam)
    if requested is None:
        return reported
    return reported if reported == requested else requested


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _float_attr(obj: Any, name: str, default: Optional[float] = None) -> Optional[float]:
    if obj is None:
        return default
    raw = getattr(obj, name, None)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _range_min_max(rng: Any) -> Optional[Tuple[float, float]]:
    if rng is None:
        return None
    lo = _float_attr(rng, "Min")
    hi = _float_attr(rng, "Max")
    if lo is None or hi is None:
        xr = getattr(rng, "XRange", None)
        if xr is not None:
            lo = _float_attr(xr, "Min")
            hi = _float_attr(xr, "Max")
    if lo is None or hi is None or hi <= lo:
        return None
    return lo, hi


def read_zoom_limits(cam) -> Tuple[float, float]:
    """Return camera-reported zoom range (usually 0.0 wide – 1.0 tele)."""
    try:
        ptz = cam.create_ptz_service()
        profiles = cam.create_media_service().GetProfiles()
        if not profiles:
            return 0.0, 1.0
        ptz_cfg = getattr(profiles[0], "PTZConfiguration", None)
        token = getattr(ptz_cfg, "token", None) if ptz_cfg else None
        if token:
            opts = ptz.GetConfigurationOptions({"ConfigurationToken": token})
            spaces = getattr(getattr(opts, "Spaces", None), "ZoomPositionSpace", None)
            if spaces:
                for space in spaces:
                    parsed = _range_min_max(getattr(space, "XRange", None))
                    if parsed:
                        return parsed
            cfg = ptz.GetConfiguration({"PTZConfigurationToken": token})
            parsed = _range_min_max(getattr(getattr(cfg, "ZoomLimits", None), "Range", None))
            if parsed:
                return parsed
    except Exception:
        pass
    return 0.0, 1.0


def read_focus_limits(cam) -> Tuple[float, float]:
    """Return camera-reported manual focus range (usually 0.0 near – 1.0 far)."""
    try:
        vs_token = _video_source_token(cam)
        imaging = cam.create_imaging_service()
        opts = imaging.GetOptions({"VideoSourceToken": vs_token})
        focus_opts = getattr(opts, "Focus", None)
        if focus_opts is not None:
            lo = _float_attr(focus_opts, "NearLimit", 0.0)
            hi = _float_attr(focus_opts, "FarLimit", 1.0)
            if hi > lo:
                return lo, hi
        settings = imaging.GetImagingSettings({"VideoSourceToken": vs_token})
        focus = getattr(settings, "Focus", None)
        if focus is not None:
            lo = _float_attr(focus, "NearLimit", 0.0)
            hi = _float_attr(focus, "FarLimit", 1.0)
            if hi > lo:
                return lo, hi
    except Exception:
        pass
    return 0.0, 1.0


def _clamp_range(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return _clamp01(value)
    return max(lo, min(hi, float(value)))


def read_lens_position(cam) -> Tuple[float, float]:
    """Return normalised (zoom, focus) in 0.0–1.0 from ONVIF."""
    zmin, zmax = read_zoom_limits(cam)
    fmin, fmax = read_focus_limits(cam)
    _, _, zoom = _current_ptz_position(cam)
    zoom = _clamp_range(zoom, zmin, zmax)

    focus = (fmin + fmax) / 2.0
    try:
        vs_token = _video_source_token(cam)
        settings = cam.create_imaging_service().GetImagingSettings({"VideoSourceToken": vs_token})
        focus_obj = getattr(settings, "Focus", None)
        if focus_obj is not None:
            raw = getattr(focus_obj, "Position", None)
            if raw is not None:
                focus = _clamp_range(float(raw), fmin, fmax)
    except Exception:
        pass
    return zoom, focus


def read_preset_position(cam) -> Tuple[float, float]:
    """Read settled PTZ zoom for preset storage; focus is display-only metadata."""
    lens_stop(cam)
    time.sleep(0.35)
    _, _, zoom = _current_ptz_position(cam)
    zmin, zmax = read_zoom_limits(cam)
    zoom = _clamp_range(zoom, zmin, zmax)
    time.sleep(0.2)
    _, _, zoom2 = _current_ptz_position(cam)
    zoom2 = _clamp_range(zoom2, zmin, zmax)
    if abs(zoom2 - zoom) <= PRESET_TOLERANCE:
        zoom = zoom2
    _, focus = read_lens_position(cam)
    return zoom, focus


def read_lens_position_for_save(cam) -> Tuple[float, float]:
    """Deprecated alias — presets use PTZ zoom only."""
    return read_preset_position(cam)


def lens_state(cam) -> Dict[str, Any]:
    zoom, focus = read_lens_position(cam)
    zmin, zmax = read_zoom_limits(cam)
    fmin, fmax = read_focus_limits(cam)
    return {
        "ok": True,
        "zoom": zoom,
        "focus": focus,
        "zoomMin": zmin,
        "zoomMax": zmax,
        "focusMin": fmin,
        "focusMax": fmax,
        "autofocus": read_autofocus_state(cam),
    }


def _current_ptz_position(cam) -> Tuple[float, float, float]:
    """Return pan, tilt, zoom from PTZ status."""
    token = _profile_token(cam)
    pan, tilt, zoom = 0.0, 0.0, 0.0
    try:
        status = cam.create_ptz_service().GetStatus({"ProfileToken": token})
        pos = getattr(status, "Position", None)
        if pos:
            pt = getattr(pos, "PanTilt", None)
            if pt is not None:
                pan = float(getattr(pt, "x", 0.0) or 0.0)
                tilt = float(getattr(pt, "y", 0.0) or 0.0)
            zm = getattr(pos, "Zoom", None)
            if zm is not None:
                zoom = float(getattr(zm, "x", 0.0) or 0.0)
    except Exception:
        pass
    return pan, tilt, zoom


def _stop_zoom(cam) -> None:
    token = _profile_token(cam)
    try:
        cam.create_ptz_service().Stop({"ProfileToken": token, "PanTilt": False, "Zoom": True})
    except Exception:
        pass


def _wait_for_zoom_settle(
    cam,
    target: float,
    zmin: float,
    zmax: float,
    *,
    timeout: float = ZOOM_MOVE_TIMEOUT_S,
) -> bool:
    target = _clamp_range(target, zmin, zmax)
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, _, zoom = _current_ptz_position(cam)
        zoom = _clamp_range(zoom, zmin, zmax)
        if abs(zoom - target) <= PRESET_TOLERANCE:
            return True
        time.sleep(0.12)
    return False


def apply_lens_zoom(cam, zoom: float, *, wait: bool = True, **_kwargs: Any) -> bool:
    """Move zoom via PTZ AbsoluteMove only — pan/tilt unchanged, no focus commands."""
    lens_stop(cam)
    zmin, zmax = read_zoom_limits(cam)
    target = _clamp_range(zoom, zmin, zmax)
    token = _profile_token(cam)
    ptz = cam.create_ptz_service()
    pan, tilt, cur_zoom = _current_ptz_position(cam)
    cur_zoom = _clamp_range(cur_zoom, zmin, zmax)

    if abs(target - cur_zoom) <= PRESET_TOLERANCE:
        return True

    # Fixed turrets (e.g. UNV IPC3638) reject PanTilt in AbsoluteMove — zoom-only works.
    attempts: list[Dict[str, Any]] = [
        {"ProfileToken": token, "Position": {"Zoom": {"x": target}}},
        {
            "ProfileToken": token,
            "Position": {"Zoom": {"x": target}},
            "Speed": {"Zoom": {"x": 0.5}},
        },
        {
            "ProfileToken": token,
            "Position": {
                "PanTilt": {"x": pan, "y": tilt},
                "Zoom": {"x": target},
            },
        },
    ]

    moved = False
    last_err: Optional[Exception] = None
    for payload in attempts:
        try:
            ptz.AbsoluteMove(payload)
            moved = True
            break
        except Exception as exc:
            last_err = exc
            continue

    if not moved:
        delta = target - cur_zoom
        if abs(delta) >= 0.001:
            try:
                ptz.RelativeMove(
                    {
                        "ProfileToken": token,
                        "Translation": {"Zoom": {"x": delta}},
                    }
                )
                moved = True
            except Exception as exc:
                last_err = exc

    if not moved:
        print(
            f"ldrs-lens-zoom: AbsoluteMove failed target={target:.4f} cur={cur_zoom:.4f} "
            f"err={last_err}",
            file=sys.stderr,
        )
        return False

    if wait:
        time.sleep(min(3.0, max(0.35, abs(target - cur_zoom) * 2.5)))
        _wait_for_zoom_settle(cam, target, zmin, zmax)

    _stop_zoom(cam)
    _, _, final_zoom = _current_ptz_position(cam)
    final_zoom = _clamp_range(final_zoom, zmin, zmax)
    return (
        abs(final_zoom - target) <= PRESET_TOLERANCE
        or abs(final_zoom - cur_zoom) > PRESET_TOLERANCE
    )


def is_autofocus_enabled(cam) -> bool:
    """True when the camera will auto-refocus (AUTO or OnceAfterMove after zoom)."""
    for vs_token in _iter_video_source_tokens(cam):
        try:
            settings = _imaging_service(cam).GetImagingSettings({"VideoSourceToken": vs_token})
            focus = getattr(settings, "Focus", None)
            if focus is None:
                continue
            mode = str(getattr(focus, "AutoFocusMode", "") or "").upper()
            if mode in ("AUTO", "AF"):
                return True
            af_mode = str(getattr(focus, "AFMode", "") or "").upper()
            if "ONCE" in af_mode and "MOVE" in af_mode:
                return True
            if mode == "MANUAL":
                return False
        except Exception:
            continue
    return False


def _apply_focus_fields(
    focus: Any,
    *,
    manual: bool,
    target: Optional[float],
    fmin: float,
    fmax: float,
) -> None:
    mode = "MANUAL" if manual else "AUTO"
    focus.AutoFocusMode = mode
    if manual and target is not None:
        focus.Position = target
    if getattr(focus, "DefaultSpeed", None) is not None:
        focus.DefaultSpeed = FOCUS_MOVE_SPEED
    if getattr(focus, "NearLimit", None) is not None:
        focus.NearLimit = fmin
    if getattr(focus, "FarLimit", None) is not None:
        focus.FarLimit = fmax
    if manual and hasattr(focus, "AFMode"):
        try:
            af_mode = str(getattr(focus, "AFMode", "") or "").upper()
            if "ONCE" in af_mode or af_mode in ("AUTO", "AF"):
                focus.AFMode = "Manual"
        except Exception:
            pass
    elif not manual and hasattr(focus, "AFMode"):
        try:
            focus.AFMode = "Auto"
        except Exception:
            pass


def _focus_mode_matches(cam, *, manual: bool) -> bool:
    return is_autofocus_enabled(cam) != manual


def _set_focus_mode_simple(
    cam,
    imaging,
    *,
    manual: bool,
    target: Optional[float],
    fmin: float,
    fmax: float,
) -> bool:
    """Partial Focus payload — works on Uniview when full settings merge fails."""
    global _IMAGING_VS_TOKEN
    mode = "MANUAL" if manual else "AUTO"
    payload: Dict[str, Any] = {
        "AutoFocusMode": mode,
        "DefaultSpeed": FOCUS_MOVE_SPEED,
        "NearLimit": fmin,
        "FarLimit": fmax,
    }
    if manual and target is not None:
        payload["Position"] = target
    if manual:
        payload["AFMode"] = "Manual"
    else:
        payload["AFMode"] = "Auto"
    for vs_token in _iter_video_source_tokens(cam):
        try:
            imaging.SetImagingSettings(
                {
                    "VideoSourceToken": vs_token,
                    "ImagingSettings": {"Focus": payload},
                    "ForcePersistence": True,
                }
            )
            _IMAGING_VS_TOKEN = vs_token
            time.sleep(0.15)
            if _focus_mode_matches(cam, manual=manual):
                return True
        except Exception:
            continue
    return False


def _configure_focus_mode(
    cam,
    *,
    manual: bool,
    position: Optional[float] = None,
    stop_first: bool = True,
) -> bool:
    """Set auto/manual focus — merge full imaging settings (required by Uniview/ONVIF)."""
    global _IMAGING_VS_TOKEN
    if stop_first:
        lens_stop(cam)
    fmin, fmax = read_focus_limits(cam)
    imaging = _imaging_service(cam)
    target = None
    if manual:
        if position is not None:
            target = _clamp_range(position, fmin, fmax)
        else:
            _, read_focus = read_lens_position(cam)
            target = _clamp_range(read_focus, fmin, fmax)

    for vs_token in _iter_video_source_tokens(cam):
        try:
            settings = imaging.GetImagingSettings({"VideoSourceToken": vs_token})
            focus = getattr(settings, "Focus", None)
            if focus is not None:
                _apply_focus_fields(
                    focus, manual=manual, target=target, fmin=fmin, fmax=fmax
                )
                imaging.SetImagingSettings(
                    {
                        "VideoSourceToken": vs_token,
                        "ImagingSettings": settings,
                        "ForcePersistence": True,
                    }
                )
                _IMAGING_VS_TOKEN = vs_token
                time.sleep(0.15)
                if _focus_mode_matches(cam, manual=manual):
                    return True
        except Exception:
            continue

    if _set_focus_mode_simple(
        cam, imaging, manual=manual, target=target, fmin=fmin, fmax=fmax
    ):
        return True

    return _focus_mode_matches(cam, manual=manual)


def disable_autofocus(cam, *, focus: Optional[float] = None, stop_first: bool = True) -> bool:
    """Turn off auto-focus and keep manual focus at the given or current position."""
    return _configure_focus_mode(cam, manual=True, position=focus, stop_first=stop_first)


def set_autofocus_enabled(cam, enabled: bool) -> bool:
    if enabled:
        return _configure_focus_mode(cam, manual=False, stop_first=True)
    _, focus = read_lens_position(cam)
    return disable_autofocus(cam, focus=focus, stop_first=False)


def hold_manual_focus(cam, focus: float, *, seconds: float = FOCUS_HOLD_S) -> None:
    """Keep manual focus locked while the camera finishes zoom / AF cycles."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if is_autofocus_enabled(cam):
            disable_autofocus(cam, focus=focus, stop_first=False)
        time.sleep(0.35)
    disable_autofocus(cam, focus=focus, stop_first=False)


def ensure_autofocus_stays_off(cam, *, focus: Optional[float] = None) -> None:
    """Re-assert manual focus if the camera turned auto-focus back on."""
    if not is_autofocus_enabled(cam):
        return
    disable_autofocus(cam, focus=focus, stop_first=False)


def ensure_manual_focus(cam) -> None:
    """Disable auto-focus so zoom moves do not refocus the lens."""
    disable_autofocus(cam)


def _apply_lens_focus_once(cam, target: float) -> bool:
    fmin, fmax = read_focus_limits(cam)
    target = _clamp_range(target, fmin, fmax)
    vs_token = _video_source_token(cam)
    _configure_focus_mode(cam, manual=True, position=target, stop_first=False)
    try:
        _imaging_service(cam).Move(
            {
                "VideoSourceToken": vs_token,
                "Focus": {
                    "Absolute": {"Position": target, "Speed": FOCUS_MOVE_SPEED},
                },
            }
        )
        return True
    except Exception:
        return False


def apply_lens_focus(cam, focus: float, *, complete: bool = False) -> bool:
    """Move focus to a normalised position."""
    attempts = 2 if complete else 1
    ok = False
    for attempt in range(attempts):
        ok = _apply_lens_focus_once(cam, focus) or ok
        if ok and not complete:
            return True
        if complete and attempt + 1 < attempts:
            time.sleep(0.25)
    if ok:
        disable_autofocus(cam, focus=focus, stop_first=False)
    return ok


def set_lens_position(
    cam,
    *,
    zoom: Optional[float] = None,
    focus: Optional[float] = None,
) -> Dict[str, Any]:
    zmin, zmax = read_zoom_limits(cam)
    fmin, fmax = read_focus_limits(cam)
    cur_z, cur_f = read_lens_position(cam)
    new_z = _clamp_range(zoom, zmin, zmax) if zoom is not None else cur_z
    new_f = _clamp_range(focus, fmin, fmax) if focus is not None else cur_f

    zoom_ok = True
    focus_ok = True
    if zoom is not None:
        zoom_ok = apply_lens_zoom(cam, new_z)
    if focus is not None:
        focus_ok = apply_lens_focus(cam, new_f, complete=True)

    result = lens_state(cam)
    if zoom is not None:
        result["zoomRead"] = result["zoom"]
        result["zoom"] = new_z if zoom_ok else result["zoom"]
    if focus is not None:
        result["focusRead"] = result["focus"]
        result["focus"] = new_f if focus_ok else result["focus"]

    if not zoom_ok or not focus_ok:
        result["ok"] = False
        if not zoom_ok and not focus_ok:
            result["error"] = "lens_move_failed"
        elif not zoom_ok:
            result["error"] = "zoom_move_failed"
        else:
            result["error"] = "focus_move_failed"
    return result


def apply_lens_position(cam, zoom: float, focus: float, *, onvif_preset_token: Optional[str] = None) -> None:
    if onvif_preset_token:
        apply_preset_to_camera(
            cam,
            {"id": "", "zoom": zoom, "focus": focus, "onvifPresetToken": onvif_preset_token},
        )
        return
    apply_lens_zoom(cam, zoom)
    apply_lens_focus(cam, focus)


def _log_preset_apply(info: Dict[str, Any]) -> None:
    print(
        "ldrs-lens-preset: "
        f"id={info.get('presetId') or '-'} "
        f"goto={info.get('usedGotoPreset')} "
        f"token={info.get('onvifPresetToken') or '-'} "
        f"manual={info.get('manualFallback')} "
        f"zoom_only={info.get('zoomOnly')}",
        file=sys.stderr,
    )


def _onvif_action_not_implemented(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "not implemented" in msg or "optional action" in msg


def camera_onvif_presets_supported(cam) -> bool:
    """True when the camera implements ONVIF GetPresets / SetPreset / GotoPreset."""
    global _ONVIF_PRESETS_SUPPORTED
    if _ONVIF_PRESETS_SUPPORTED is not None:
        return _ONVIF_PRESETS_SUPPORTED
    profile_token = _profile_token(cam)
    ptz = cam.create_ptz_service()
    try:
        ptz.GetPresets({"ProfileToken": profile_token})
        _ONVIF_PRESETS_SUPPORTED = True
    except Exception as exc:
        if _onvif_action_not_implemented(exc):
            _ONVIF_PRESETS_SUPPORTED = False
        else:
            raise
    print(
        f"ldrs-lens-preset: onvif_presets_supported={_ONVIF_PRESETS_SUPPORTED}",
        file=sys.stderr,
    )
    return _ONVIF_PRESETS_SUPPORTED


def apply_preset_to_camera(cam, preset: Dict[str, Any]) -> Dict[str, Any]:
    """Recall a preset — GotoPreset when supported, otherwise PTZ zoom only."""
    preset_id = str(preset.get("id") or "")
    onvif_token = preset.get("onvifPresetToken")
    if onvif_token and not str(onvif_token).strip():
        onvif_token = None
    info: Dict[str, Any] = {
        "presetId": preset_id,
        "usedGotoPreset": False,
        "onvifPresetToken": onvif_token,
        "manualFallback": False,
        "zoomOnly": False,
        "onvifPresetsSupported": camera_onvif_presets_supported(cam),
    }

    if onvif_token and info["onvifPresetsSupported"]:
        profile_token = _profile_token(cam)
        ptz = cam.create_ptz_service()
        try:
            ptz.GotoPreset({"ProfileToken": profile_token, "PresetToken": str(onvif_token)})
        except Exception as exc:
            raise RuntimeError(f"goto_preset_failed:{exc}") from exc
        time.sleep(GOTO_PRESET_SETTLE_S)
        lens_stop(cam)
        info["usedGotoPreset"] = True
        _log_preset_apply(info)
        return info

    if onvif_token and not info["onvifPresetsSupported"]:
        print(
            f"ldrs-lens-preset: ignoring onvifPresetToken={onvif_token} "
            "(camera does not support ONVIF presets)",
            file=sys.stderr,
        )

    zoom = float(preset.get("zoom", 0.0) or 0.0)
    apply_lens_zoom(cam, zoom)
    info["manualFallback"] = True
    info["zoomOnly"] = True
    _log_preset_apply(info)
    return info


def _marker_key(ip: str, preset_id: str) -> str:
    return f"{ip}:{preset_id}"


def mark_preset_applied(ip: str, preset_id: str) -> None:
    LENS_APPLIED_MARKER.parent.mkdir(parents=True, exist_ok=True)
    LENS_APPLIED_MARKER.write_text(f"{_marker_key(ip, preset_id)}:{time.time():.0f}\n", encoding="utf-8")


def preset_already_applied(ip: str, preset_id: str) -> bool:
    if not LENS_APPLIED_MARKER.is_file():
        return False
    line = LENS_APPLIED_MARKER.read_text(encoding="utf-8").strip()
    return line.startswith(_marker_key(ip, preset_id))


def positions_match(
    actual: Tuple[float, float],
    expected: Tuple[float, float],
    tolerance: float = PRESET_TOLERANCE,
) -> bool:
    az, af = actual
    ez, ef = expected
    return abs(az - ez) <= tolerance and abs(af - ef) <= tolerance


def preset_expected_zoom(preset: Dict[str, Any]) -> float:
    return float(preset.get("zoom", 0.0) or 0.0)


def preset_zoom_matches(cam, preset: Dict[str, Any], tolerance: float = PRESET_TOLERANCE) -> bool:
    _, _, actual_z = _current_ptz_position(cam)
    zmin, zmax = read_zoom_limits(cam)
    actual_z = _clamp_range(actual_z, zmin, zmax)
    return abs(actual_z - preset_expected_zoom(preset)) <= tolerance


def apply_active_preset(*, force: bool = False) -> Dict[str, Any]:
    """Ensure the camera lens matches the selected preset.

    On boot (/run cleared) the first connect reads zoom/focus and corrects drift.
    Later resolve ticks skip ONVIF unless force=True (assign, relocate, reconfigure).
    """
    if not onvif_available():
        return {"ok": False, "error": "onvif_not_installed"}
    presets = load_presets()
    active_id = (presets.get("activePresetId") or "").strip()
    if not active_id:
        return {"ok": False, "error": "no_active_preset"}
    preset = find_preset(presets, active_id)
    if not preset:
        return {"ok": False, "error": "preset_not_found"}

    env = load_env(SPORTASSIST_ETC / "camera.env")
    ip = env.get("CAMERA_IP", "").strip()
    if not ip or not env.get("CAMERA_USERNAME") or not env.get("CAMERA_PASSWORD"):
        return {"ok": False, "error": "camera_not_configured"}
    if not force and preset_already_applied(ip, active_id):
        return {"ok": True, "skipped": True, "presetId": active_id}

    cam = camera_from_env()
    onvif_token = preset.get("onvifPresetToken")
    use_goto = bool(onvif_token) and camera_onvif_presets_supported(cam)
    matched = False
    corrected = False

    if force or use_goto:
        apply_info = apply_preset_to_camera(cam, preset)
        corrected = True
    else:
        if preset_zoom_matches(cam, preset):
            matched = True
            apply_info = {
                "presetId": active_id,
                "usedGotoPreset": False,
                "onvifPresetToken": onvif_token,
                "manualFallback": False,
                "zoomOnly": False,
                "skippedMove": True,
            }
        else:
            apply_info = apply_preset_to_camera(cam, preset)
            corrected = True

    mark_preset_applied(ip, active_id)
    result: Dict[str, Any] = {
        "ok": True,
        "presetId": active_id,
        "matched": matched,
        "corrected": corrected,
        **apply_info,
    }
    if not matched and not use_goto:
        result["expected"] = {"zoom": preset_expected_zoom(preset)}
    return result


def nudge_zoom(cam, direction: str) -> None:
    """Move zoom one small step per click (PTZ AbsoluteMove only)."""
    _, _, zoom = _current_ptz_position(cam)
    zmin, zmax = read_zoom_limits(cam)
    zoom = _clamp_range(zoom, zmin, zmax)
    delta = ZOOM_STEP if direction in ("in", "up", "right") else -ZOOM_STEP
    apply_lens_zoom(cam, _clamp_range(zoom + delta, zmin, zmax))


def nudge_focus(cam, direction: str) -> None:
    """Move focus one small step per click."""
    lens_stop(cam)
    delta = FOCUS_STEP if direction in ("in", "near") else -FOCUS_STEP
    vs_token = _video_source_token(cam)
    imaging = cam.create_imaging_service()
    try:
        imaging.Move(
            {
                "VideoSourceToken": vs_token,
                "Focus": {
                    "Relative": {"Distance": delta, "Speed": FOCUS_MOVE_SPEED},
                },
            }
        )
        return
    except Exception:
        pass
    try:
        imaging.Move(
            {
                "VideoSourceToken": vs_token,
                "Focus": {
                    "Absolute": {
                        "Position": _clamp01(read_lens_position(cam)[1] + delta),
                        "Speed": FOCUS_MOVE_SPEED,
                    },
                },
            }
        )
        return
    except Exception:
        pass
    _, focus = read_lens_position(cam)
    new_focus = _clamp01(focus + delta)
    imaging.SetImagingSettings(
        {
            "VideoSourceToken": vs_token,
            "ImagingSettings": {
                "Focus": {
                    "AutoFocusMode": "MANUAL",
                    "DefaultSpeed": FOCUS_MOVE_SPEED,
                    "NearLimit": 0.0,
                    "FarLimit": 1.0,
                    "Position": new_focus,
                }
            },
            "ForcePersistence": True,
        }
    )


def ptz_move(cam, axis: str, direction: str) -> None:
    if axis == "zoom":
        nudge_zoom(cam, direction)
        return

    if axis == "focus":
        nudge_focus(cam, direction)
        return

    token = _profile_token(cam)
    speed = MOVE_SPEED if direction in ("in", "up", "right") else -MOVE_SPEED
    vel = {"PanTilt": {"x": 0, "y": 0}, "Zoom": {"x": 0}}
    if axis == "pan":
        vel["PanTilt"]["x"] = speed
    else:
        vel["PanTilt"]["y"] = speed
    cam.create_ptz_service().ContinuousMove({"ProfileToken": token, "Velocity": vel})


def lens_stop(cam) -> None:
    token = _profile_token(cam)
    try:
        cam.create_ptz_service().Stop({"ProfileToken": token, "PanTilt": True, "Zoom": True})
    except Exception:
        pass
    try:
        cam.create_imaging_service().Stop({"VideoSourceToken": _video_source_token(cam)})
    except Exception:
        pass


def imaging_autofocus(cam) -> None:
    set_autofocus_enabled(cam, True)


def list_camera_onvif_presets(cam) -> Dict[str, Any]:
    """List presets stored on the camera (ONVIF GetPresets)."""
    if not camera_onvif_presets_supported(cam):
        return {"supported": False, "presets": []}
    profile_token = _profile_token(cam)
    ptz = cam.create_ptz_service()
    raw = ptz.GetPresets({"ProfileToken": profile_token}) or []
    out: list[Dict[str, Any]] = []
    for item in raw:
        token = getattr(item, "token", None)
        if not token:
            continue
        name = getattr(item, "Name", None) or getattr(item, "name", None) or ""
        out.append({"token": str(token), "name": str(name)})
    return {"supported": True, "presets": out}


def save_onvif_preset_to_camera(
    cam,
    name: str,
    preset_token: Optional[str] = None,
) -> str:
    """Store the camera's current PTZ position as an onboard preset."""
    profile_token = _profile_token(cam)
    ptz = cam.create_ptz_service()
    payload: Dict[str, Any] = {"ProfileToken": profile_token, "PresetName": name}
    if preset_token:
        payload["PresetToken"] = str(preset_token)
    try:
        result = ptz.SetPreset(payload)
    except Exception as exc:
        raise RuntimeError(f"onvif_set_preset_failed:{exc}") from exc
    token = getattr(result, "PresetToken", None) or preset_token
    if not token:
        raise RuntimeError("onvif_set_preset_no_token")
    return str(token)


def recall_preset(presets: Dict[str, Any], preset_id: str, cam) -> Dict[str, Any]:
    preset = find_preset(presets, preset_id)
    if not preset:
        raise RuntimeError("preset_not_found")
    apply_info = apply_preset_to_camera(cam, preset)
    presets["activePresetId"] = preset_id
    save_presets(presets)
    env = load_env(SPORTASSIST_ETC / "camera.env")
    mark_preset_applied(env.get("CAMERA_IP", "").strip(), preset_id)
    zmin, zmax = read_zoom_limits(cam)
    fmin, fmax = read_focus_limits(cam)
    zoom = float(preset.get("zoom", 0.0) or 0.0)
    focus = float(preset.get("focus", 0.5) or 0.5)
    return {
        "ok": True,
        "id": preset_id,
        "label": preset.get("label", preset_id),
        "zoom": zoom,
        "focus": focus,
        "zoomMin": zmin,
        "zoomMax": zmax,
        "focusMin": fmin,
        "focusMax": fmax,
        "autofocus": read_autofocus_state(cam),
        "onvifPresetToken": preset.get("onvifPresetToken"),
        **apply_info,
    }


def save_preset(
    presets: Dict[str, Any],
    preset_id: str,
    label: str,
    cam,
) -> Dict[str, Any]:
    zoom, focus = read_preset_position(cam)
    found = False
    for preset in presets.get("presets", []):
        if preset.get("id") == preset_id:
            preset["label"] = label
            preset["zoom"] = zoom
            preset["focus"] = focus
            preset["onvifPresetToken"] = None
            found = True
            break
    if not found:
        preset_list = presets.setdefault("presets", [])
        if len(preset_list) >= MAX_PRESETS:
            raise RuntimeError("preset_limit_reached")
        preset_list.append(
            {
                "id": preset_id,
                "label": label,
                "zoom": zoom,
                "focus": focus,
                "onvifPresetToken": None,
            }
        )
    if not presets.get("activePresetId"):
        presets["activePresetId"] = preset_id
    save_presets(presets)
    saved = find_preset(presets, preset_id) or {}
    print(
        f"ldrs-lens-preset: saved local id={preset_id} zoom={zoom:.3f} focus={focus:.3f}",
        file=sys.stderr,
    )
    return saved


def save_preset_onvif(
    presets: Dict[str, Any],
    preset_id: str,
    label: str,
    cam,
) -> Dict[str, Any]:
    """Save preset — camera ONVIF preset when supported, else local PTZ zoom."""
    if not camera_onvif_presets_supported(cam):
        return save_preset(presets, preset_id, label, cam)

    zoom, focus = read_preset_position(cam)
    existing_token: Optional[str] = None
    found = False
    for preset in presets.get("presets", []):
        if preset.get("id") == preset_id:
            existing_token = preset.get("onvifPresetToken")
            preset["label"] = label
            preset["zoom"] = zoom
            preset["focus"] = focus
            found = True
            break
    onvif_token = save_onvif_preset_to_camera(cam, label, existing_token)
    if found:
        for preset in presets.get("presets", []):
            if preset.get("id") == preset_id:
                preset["onvifPresetToken"] = onvif_token
                break
    else:
        preset_list = presets.setdefault("presets", [])
        if len(preset_list) >= MAX_PRESETS:
            raise RuntimeError("preset_limit_reached")
        preset_list.append(
            {
                "id": preset_id,
                "label": label,
                "zoom": zoom,
                "focus": focus,
                "onvifPresetToken": onvif_token,
            }
        )
    if not presets.get("activePresetId"):
        presets["activePresetId"] = preset_id
    save_presets(presets)
    saved = find_preset(presets, preset_id) or {}
    print(
        f"ldrs-lens-preset: saved id={preset_id} onvif_token={onvif_token} zoom={zoom:.3f} focus={focus:.3f}",
        file=sys.stderr,
    )
    return saved


def delete_preset(presets: Dict[str, Any], preset_id: str) -> None:
    remaining = [p for p in presets.get("presets", []) if p.get("id") != preset_id]
    if not any(p.get("id") == preset_id for p in presets.get("presets", [])):
        raise RuntimeError("preset_not_found")
    if len(remaining) < MIN_PRESETS:
        raise RuntimeError("preset_minimum")
    presets["presets"] = remaining
    if presets.get("activePresetId") == preset_id:
        presets["activePresetId"] = remaining[0]["id"] if remaining else ""
    save_presets(presets)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: onvif_lens.py move|stop|autofocus|preset|apply-active ...", file=sys.stderr)
        return 2
    if not onvif_available():
        print(json.dumps({"ok": False, "error": "onvif_not_installed"}))
        return 1
    cmd = sys.argv[1]
    try:
        _acquire_lens_lock()
        if cmd == "apply-active":
            force = len(sys.argv) >= 3 and sys.argv[2] == "--force"
            result = apply_active_preset(force=force)
            print(json.dumps(result))
            return 0 if result.get("ok") else 1

        cam = camera_from_env()
        if cmd == "state":
            print(json.dumps(lens_state(cam)))
            return 0
        if cmd == "set-position":
            zoom = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
            focus = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] != "-" else None
            if zoom is None and focus is None:
                return 2
            result = set_lens_position(cam, zoom=zoom, focus=focus)
            print(json.dumps(result))
            return 0 if result.get("ok") else 1
        if cmd == "move" and len(sys.argv) >= 4:
            ptz_move(cam, sys.argv[2], sys.argv[3])
        elif cmd == "stop":
            lens_stop(cam)
        elif cmd == "autofocus":
            imaging_autofocus(cam)
        elif cmd == "set-autofocus" and len(sys.argv) >= 3:
            enabled = sys.argv[2].lower() in ("1", "on", "true", "yes")
            try:
                ok = set_autofocus_enabled(cam, enabled)
            except Exception as exc:
                print(json.dumps({"ok": False, "error": str(exc)}))
                return 1
            reported = is_autofocus_enabled(cam)
            ok = ok or reported == enabled
            body: Dict[str, Any] = {"ok": ok, "autofocus": reported}
            if not ok:
                body["error"] = "focus_mode_auto_failed" if enabled else "focus_mode_manual_failed"
            print(json.dumps(body))
            return 0 if ok else 1
        elif cmd == "preset" and len(sys.argv) >= 3:
            sub = sys.argv[2]
            presets = load_presets()
            if sub == "recall" and len(sys.argv) >= 4:
                result = recall_preset(presets, sys.argv[3], cam)
                print(json.dumps(result))
                return 0
            elif sub == "list-onvif":
                result = list_camera_onvif_presets(cam)
                print(json.dumps({"ok": True, **result}))
                return 0
            elif sub == "save-onvif" and len(sys.argv) >= 5:
                saved = save_preset_onvif(presets, sys.argv[3], sys.argv[4], cam)
                print(json.dumps({"ok": True, **saved}))
                return 0
            elif sub == "save" and len(sys.argv) >= 5:
                saved = save_preset(presets, sys.argv[3], sys.argv[4], cam)
                print(json.dumps({"ok": True, **saved}))
                return 0
            elif sub == "delete" and len(sys.argv) >= 4:
                delete_preset(presets, sys.argv[3])
            else:
                return 2
        else:
            return 2
        print(json.dumps({"ok": True}))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    finally:
        _release_lens_lock()


if __name__ == "__main__":
    raise SystemExit(main())
