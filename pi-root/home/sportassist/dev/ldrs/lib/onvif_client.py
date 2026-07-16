"""ONVIF helpers — requires onvif-zeep on the Pi."""
from __future__ import annotations

import functools
import re
import socket
import sysconfig
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from onvif import ONVIFCamera
except ImportError:
    ONVIFCamera = None  # type: ignore

WSDiscovery = None
try:
    from wsdiscovery import WSDiscovery
except ImportError:
    try:
        from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
    except ImportError:
        WSDiscovery = None


def onvif_available() -> bool:
    return ONVIFCamera is not None


@functools.lru_cache(maxsize=1)
def onvif_wsdl_dir() -> str:
    """Find devicemgmt.wsdl — pip often installs under site-packages, not dist-packages."""
    roots: list[Path] = []
    for key in ("purelib", "platlib"):
        p = sysconfig.get_path(key)
        if p:
            roots.append(Path(p))
    try:
        import onvif

        pkg = Path(onvif.__file__).resolve().parent
        roots.extend([pkg, pkg.parent])
    except ImportError:
        pass
    local_lib = Path("/home/sportassist/.local/lib")
    if local_lib.is_dir():
        roots.extend(local_lib.glob("python3.*/site-packages"))
    bundled = Path("/home/sportassist/dev/ldrs/wsdl")
    if bundled.is_dir():
        roots.append(bundled)

    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for candidate in (root / "wsdl", root):
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if (candidate / "devicemgmt.wsdl").is_file():
                return str(candidate)
        for hit in root.rglob("devicemgmt.wsdl"):
            return str(hit.parent)

    raise RuntimeError(
        "onvif-zeep WSDL files not found — reinstall with §4.1 "
        "(sudo pip3 install --ignore-installed isodate -r requirements-pip.txt)"
    )


DEFAULT_ONVIF_PORTS = (80, 8080, 443)
_RTSP_PORTS = frozenset({554, 8554, 1935})


def _tcp_open(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def connect_onvif(
    ip: str,
    username: str,
    password: str,
    port: Optional[int] = None,
) -> Any:
    """Connect ONVIF — never use RTSP port 554 (hangs)."""
    if not ONVIFCamera:
        raise RuntimeError("onvif-zeep not installed")
    if port and port not in _RTSP_PORTS:
        candidates = [port]
    else:
        candidates = [p for p in DEFAULT_ONVIF_PORTS if _tcp_open(ip, p)]
        if not candidates:
            candidates = list(DEFAULT_ONVIF_PORTS)
    last_exc: Optional[Exception] = None
    for p in candidates:
        try:
            cam = ONVIFCamera(ip, p, username, password, onvif_wsdl_dir())
            cam.update_xaddrs()
            return cam
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(str(last_exc) if last_exc else "onvif_unreachable")


def connect(ip: str, port: int, username: str, password: str) -> Any:
    """Legacy API — port may be RTSP (554) or ONVIF (80)."""
    if port in _RTSP_PORTS:
        return connect_onvif(ip, username, password)
    return connect_onvif(ip, username, password, port=port)


_GENERIC_ONVIF_LABELS = frozenset({"device", "networkvideotransmitter", "onvif", "tds", "media"})


def is_plausible_camera_hostname(label: str) -> bool:
    """Reject WS-Discovery type URLs and other non-hostname labels."""
    if not label or len(label) > 63:
        return False
    low = label.lower()
    if "://" in label or low.startswith("http") or ".wsdl" in low or "onvif.org" in low:
        return False
    if low in _GENERIC_ONVIF_LABELS:
        return False
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", label))


def _label_from_onvif_scope(raw: str) -> str:
    """Extract device name/hardware from ONVIF scope URIs."""
    for pattern in (
        r"onvif://www\.onvif\.org/name/([^/\s?#]+)",
        r"onvif://www\.onvif\.org/hardware/([^/\s?#]+)",
        r"onvif://www\.onvif\.org/Profile/[^/]+/([^/\s?#]+)",
    ):
        m = re.search(pattern, raw, re.I)
        if m:
            candidate = m.group(1).strip()
            if is_plausible_camera_hostname(candidate):
                return candidate
    return ""


def _ws_service_name(svc: Any) -> str:
    """Device label from WS-Discovery Service (API differs between 1.x and 2.x)."""
    get_props = getattr(svc, "getProperties", None)
    if callable(get_props):
        try:
            for prop in get_props():
                pname = getattr(prop, "getName", lambda: "")()
                if pname in ("name", "Device", "hardware"):
                    val = str(getattr(prop, "getValue", lambda: "")())
                    if is_plausible_camera_hostname(val):
                        return val
        except Exception:
            pass
    try:
        for scope in svc.getScopes() or []:
            val = getattr(scope, "getValue", None)
            raw = val() if callable(val) else str(scope)
            if not raw:
                continue
            label = _label_from_onvif_scope(raw)
            if label:
                return label
    except Exception:
        pass
    try:
        for t in svc.getTypes() or []:
            local = getattr(t, "getLocalPart", None)
            if callable(local):
                label = str(local())
                if is_plausible_camera_hostname(label):
                    return label
    except Exception:
        pass
    return ""


def ws_discover(timeout: int = 5) -> List[Dict[str, str]]:
    if not WSDiscovery:
        return []
    try:
        wsd = WSDiscovery()
        wsd.start()
        services = wsd.searchServices(timeout=timeout)
        wsd.stop()
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for svc in services:
        try:
            xaddrs = svc.getXAddrs()
            if not xaddrs:
                continue
            addr = xaddrs[0]
            name = _ws_service_name(svc)
            out.append({"xaddr": addr, "name": name})
        except Exception:
            continue
    return out


def get_device_information(cam: Any) -> Dict[str, str]:
    """ONVIF GetDeviceInformation — manufacturer, model, serial, etc."""
    dev = cam.create_devicemgmt_service()
    info = dev.GetDeviceInformation()
    return {
        "Manufacturer": str(getattr(info, "Manufacturer", "") or "").strip(),
        "Model": str(getattr(info, "Model", "") or "").strip(),
        "FirmwareVersion": str(getattr(info, "FirmwareVersion", "") or "").strip(),
        "SerialNumber": str(getattr(info, "SerialNumber", "") or "").strip(),
        "HardwareId": str(getattr(info, "HardwareId", "") or "").strip(),
    }


def device_id_from_information(info: Dict[str, str]) -> str:
    """Stable identifier for matching camera after IP change."""
    serial = (info.get("SerialNumber") or "").strip()
    if serial and serial.lower() not in ("", "n/a", "unknown", "none"):
        return serial
    model = (info.get("Model") or "").strip()
    mfr = (info.get("Manufacturer") or "").strip()
    hw = (info.get("HardwareId") or "").strip()
    if hw and model:
        return f"{model}-{hw}" if not mfr else f"{mfr}-{model}-{hw}"
    if model:
        return f"{mfr}-{model}" if mfr else model
    return ""


def reported_name_from_information(info: Dict[str, str]) -> str:
    """Human-readable label from camera (model / serial)."""
    model = (info.get("Model") or "").strip()
    serial = (info.get("SerialNumber") or "").strip()
    if model and serial and serial.lower() not in ("", "n/a", "unknown"):
        return f"{model} ({serial})"
    return model or serial or ""


def get_profiles(cam: Any) -> List[Any]:
    media = cam.create_media_service()
    return media.GetProfiles()


def set_profile_sync_point(cam: Any, profile_token: str) -> None:
    """ONVIF — request immediate IDR so RTSP clients join at live edge."""
    media = cam.create_media_service()
    media.SetSynchronizationPoint({"ProfileToken": profile_token})


def prepare_live_streaming(cam: Any) -> None:
    """Best-effort: sync all encoder profiles to live; disable SD/recording modes."""
    try:
        for profile in get_profiles(cam):
            token = getattr(profile, "token", None)
            if token:
                try:
                    set_profile_sync_point(cam, token)
                except Exception:
                    pass
    except Exception:
        pass
    _disable_recording_best_effort(cam)


def _disable_recording_best_effort(cam: Any) -> None:
    """Stop ONVIF recording jobs / tracks so RTSP is live-only where supported."""
    try:
        rec = cam.create_recording_service()
    except Exception:
        return
    try:
        if hasattr(rec, "GetRecordings"):
            recordings = rec.GetRecordings()
            if recordings is None:
                return
            items = recordings if isinstance(recordings, list) else [recordings]
            for item in items:
                token = getattr(item, "token", None) or getattr(item, "Token", None)
                if not token:
                    continue
                if hasattr(rec, "DeleteRecording"):
                    try:
                        rec.DeleteRecording({"RecordingToken": token})
                    except Exception:
                        pass
    except Exception:
        pass
    try:
        if hasattr(rec, "GetRecordingJobs"):
            jobs = rec.GetRecordingJobs()
            if jobs is None:
                return
            job_list = jobs if isinstance(jobs, list) else [jobs]
            for job in job_list:
                token = getattr(job, "JobToken", None) or getattr(job, "token", None)
                if token and hasattr(rec, "DeleteRecordingJob"):
                    try:
                        rec.DeleteRecordingJob({"JobToken": token})
                    except Exception:
                        pass
    except Exception:
        pass


def get_stream_uri(cam: Any, profile_token: str) -> str:
    media = cam.create_media_service()
    uri = media.GetStreamUri(
        {
            "StreamSetup": {
                "Stream": "RTP-Unicast",
                "Transport": {"Protocol": "RTSP"},
            },
            "ProfileToken": profile_token,
        }
    )
    return uri.Uri


def parse_rtsp_path(rtsp_url: str) -> str:
    if "://" not in rtsp_url:
        return rtsp_url
    _, _, rest = rtsp_url.partition("://")
    if "@" in rest:
        _, _, rest = rest.partition("@")
    if "/" in rest:
        _, _, path = rest.partition("/")
        return "/" + path.split("?")[0]
    return "/"


def encoding_to_codec(enc: str) -> str:
    e = (enc or "").upper()
    if "265" in e or "HEVC" in e:
        return "h265"
    if "264" in e or "H264" in e:
        return "h264"
    if "JPEG" in e or "MJPEG" in e:
        return "mjpeg"
    return "unknown"


def profile_info(cam: Any, profile: Any) -> Dict[str, Any]:
    media = cam.create_media_service()
    token = profile.token
    label = getattr(profile, "Name", None) or token
    width = height = fps = 25
    codec = "h264"
    try:
        venc = profile.VideoEncoderConfiguration
        if venc:
            width = int(getattr(venc.Resolution, "Width", width))
            height = int(getattr(venc.Resolution, "Height", height))
            if hasattr(venc, "RateControl") and venc.RateControl:
                fps = int(getattr(venc.RateControl, "FrameRateLimit", fps))
            enc = getattr(venc, "Encoding", "H264")
            codec = encoding_to_codec(str(enc))
    except Exception:
        pass
    try:
        uri = get_stream_uri(cam, token)
        path = parse_rtsp_path(uri)
    except Exception:
        path = ""
    return {
        "id": token,
        "label": label,
        "width": width,
        "height": height,
        "fps": fps,
        "codec": codec,
        "rtspPath": path,
    }


def get_encoder_options(cam: Any, config_token: str) -> Dict[str, Any]:
    media = cam.create_media_service()
    opts = media.GetVideoEncoderConfigurationOptions({"ConfigurationToken": config_token})
    codecs: List[str] = []
    resolutions: List[str] = []
    try:
        for enc_opt in opts.Options:
            enc = str(getattr(enc_opt, "Encoding", ""))
            c = encoding_to_codec(enc)
            if c == "h265":
                codecs.append("h265")
                codecs.append("ultra265")
            elif c == "h264":
                codecs.append("h264")
            elif c == "mjpeg":
                codecs.append("mjpeg")
            res = getattr(enc_opt, "ResolutionsAvailable", None) or []
            for r in res:
                resolutions.append(f"{r.Width}x{r.Height}")
    except Exception:
        pass
    return {
        "codecs": sorted(set(codecs)),
        "resolutions": sorted(set(resolutions)),
    }


def set_encoder(
    cam: Any,
    profile: Any,
    width: int,
    height: int,
    fps: int,
    codec: str,
    bitrate: int,
    gop: int = 25,
) -> None:
    media = cam.create_media_service()
    venc = profile.VideoEncoderConfiguration
    if not venc:
        raise RuntimeError("Profile has no VideoEncoderConfiguration")
    venc.Resolution.Width = width
    venc.Resolution.Height = height
    if hasattr(venc, "RateControl") and venc.RateControl:
        venc.RateControl.FrameRateLimit = fps
        venc.RateControl.BitrateLimit = bitrate
    enc_map = {"h264": "H264", "h265": "H265", "ultra265": "H265"}
    venc.Encoding = enc_map.get(codec, "H264")
    if hasattr(venc, "GovLength"):
        venc.GovLength = gop
    media.SetVideoEncoderConfiguration({"Configuration": venc, "ForcePersistence": True})
