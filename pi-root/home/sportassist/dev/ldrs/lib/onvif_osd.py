#!/usr/bin/env python3
"""ONVIF on-screen display — date/time stamp toggle."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.env_util import SPORTASSIST_ETC
from lib.onvif_client import connect_onvif, onvif_available
from lib.onvif_lens import camera_from_env

OSD_CACHE_PATH = SPORTASSIST_ETC / "datestamp-osd-cache.json"
_DATE_TEXT_TYPES = frozenset({"date", "time", "dateandtime", "date_and_time"})


def _media_service(cam):
    return cam.create_media_service()


def _video_source_config_token(cam) -> str:
    profiles = _media_service(cam).GetProfiles()
    if not profiles:
        raise RuntimeError("no_onvif_profiles")
    profile = profiles[0]
    vs_cfg = getattr(profile, "VideoSourceConfiguration", None)
    if vs_cfg is not None and getattr(vs_cfg, "token", None):
        return vs_cfg.token
    return profile.token


def _list_osds(cam) -> List[Any]:
    media = _media_service(cam)
    config_token = _video_source_config_token(cam)
    for payload in (
        {"ConfigurationToken": config_token},
        {"ConfigurationToken": _media_service(cam).GetProfiles()[0].token},
        {},
    ):
        try:
            osds = media.GetOSDs(payload)
            if osds:
                return list(osds)
        except Exception:
            continue
    return []


def _osd_text_type(osd: Any) -> str:
    text = getattr(osd, "TextString", None)
    if text is None:
        return ""
    return str(getattr(text, "Type", "") or "").lower()


def _is_datestamp_osd(osd: Any) -> bool:
    osd_type = str(getattr(osd, "Type", "") or "").lower()
    if osd_type in _DATE_TEXT_TYPES:
        return True
    return _osd_text_type(osd) in _DATE_TEXT_TYPES


def _ref_token(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    inner = getattr(value, "_value_1", None)
    if inner is not None:
        return str(inner)
    return str(value)


def _serialize_osd(osd: Any) -> Dict[str, Any]:
    text = getattr(osd, "TextString", None)
    pos = getattr(osd, "Position", None)
    pos_xy = getattr(pos, "Pos", None) if pos is not None else None
    data: Dict[str, Any] = {
        "token": getattr(osd, "token", None),
        "Type": getattr(osd, "Type", "Text"),
        "VideoSourceConfigurationToken": _ref_token(
            getattr(osd, "VideoSourceConfigurationToken", None)
        ),
    }
    if pos is not None:
        data["Position"] = {
            "Type": getattr(pos, "Type", "Custom"),
            "Pos": {
                "x": float(getattr(pos_xy, "x", -0.9) or -0.9),
                "y": float(getattr(pos_xy, "y", -0.85) or -0.85),
            },
        }
    if text is not None:
        data["TextString"] = {
            "Type": getattr(text, "Type", "DateAndTime"),
            "FontSize": int(getattr(text, "FontSize", 32) or 32),
            "DateFormat": getattr(text, "DateFormat", None) or "yyyy-MM-dd",
            "TimeFormat": getattr(text, "TimeFormat", None) or "HH:mm:ss",
            "PlainText": getattr(text, "PlainText", None) or "",
        }
    return data


def _load_osd_cache() -> List[Dict[str, Any]]:
    if not OSD_CACHE_PATH.is_file():
        return []
    try:
        payload = json.loads(OSD_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = payload.get("osds", [])
    return items if isinstance(items, list) else []


def _save_osd_cache(osds: List[Dict[str, Any]], *, config_token: str) -> None:
    OSD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    OSD_CACHE_PATH.write_text(
        json.dumps({"configToken": config_token, "osds": osds}, indent=2) + "\n",
        encoding="utf-8",
    )


def _prepare_osd_payload(item: Dict[str, Any], config_token: str) -> Dict[str, Any]:
    """Build an OSD payload acceptable to Uniview (token required on CreateOSD)."""
    payload = {k: v for k, v in item.items() if v is not None}
    token = payload.get("token")
    if not token:
        payload["token"] = "osd_datestamp_0"
    payload["Type"] = payload.get("Type") or "Text"
    payload["VideoSourceConfigurationToken"] = (
        payload.get("VideoSourceConfigurationToken") or config_token
    )
    if "Position" not in payload:
        payload["Position"] = {"Type": "UpperLeft"}
    text = payload.get("TextString") or {}
    if not isinstance(text, dict):
        text = {}
    text.setdefault("Type", "DateAndTime")
    text.setdefault("FontSize", 32)
    text.setdefault("DateFormat", "yyyy-MM-dd")
    text.setdefault("TimeFormat", "HH:mm:ss")
    payload["TextString"] = text
    return payload


def _default_datestamp_osd(config_token: str) -> Dict[str, Any]:
    return _prepare_osd_payload({}, config_token)


def _restore_osd(media, item: Dict[str, Any], config_token: str) -> None:
    payload = _prepare_osd_payload(item, config_token)
    try:
        media.SetOSD({"OSD": payload})
        return
    except Exception:
        pass
    media.CreateOSD({"OSD": payload})


def _unsupported_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "not implemented" in msg or "optional action" in msg or "action not" in msg


def datestamp_state(cam) -> Dict[str, Any]:
    try:
        osds = _list_osds(cam)
    except Exception as exc:
        if _unsupported_error(exc):
            return {"ok": True, "supported": False, "enabled": None}
        return {"ok": False, "error": str(exc)}

    date_osds = [osd for osd in osds if _is_datestamp_osd(osd)]
    return {
        "ok": True,
        "supported": True,
        "enabled": len(date_osds) > 0,
        "count": len(date_osds),
    }


def set_datestamp_enabled(cam, enabled: bool) -> Dict[str, Any]:
    media = _media_service(cam)
    config_token = _video_source_config_token(cam)

    try:
        osds = _list_osds(cam)
    except Exception as exc:
        if _unsupported_error(exc):
            return {"ok": False, "error": "datestamp_not_supported", "supported": False}
        return {"ok": False, "error": str(exc)}

    date_osds = [osd for osd in osds if _is_datestamp_osd(osd)]

    if enabled:
        if date_osds:
            return {"ok": True, "supported": True, "enabled": True}
        cached = _load_osd_cache()
        items = cached if cached else [_default_datestamp_osd(config_token)]
        try:
            for item in items:
                _restore_osd(media, item, config_token)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "supported": True}
        state = datestamp_state(cam)
        return {**state, "ok": state.get("enabled", False)}

    if not date_osds:
        return {"ok": True, "supported": True, "enabled": False}

    cache = [_serialize_osd(osd) for osd in date_osds]
    _save_osd_cache(cache, config_token=config_token)
    for osd in date_osds:
        token = getattr(osd, "token", None)
        if not token:
            continue
        try:
            media.DeleteOSD({"OSDToken": token})
        except Exception as exc:
            return {"ok": False, "error": str(exc), "supported": True}
    return {"ok": True, "supported": True, "enabled": False}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: onvif_osd.py state|on|off", file=sys.stderr)
        return 2
    if not onvif_available():
        print(json.dumps({"ok": False, "error": "onvif_not_installed"}))
        return 1
    cmd = sys.argv[1]
    try:
        cam = camera_from_env()
        if cmd == "state":
            print(json.dumps(datestamp_state(cam)))
            return 0
        if cmd in ("on", "off"):
            result = set_datestamp_enabled(cam, cmd == "on")
            print(json.dumps(result))
            return 0 if result.get("ok") else 1
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
