#!/usr/bin/env python3
"""Clear saved camera identity, credentials, and stream paths from camera.env."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.buffer_util import clear_hls_buffers, stop_replay_buffer
from lib.env_util import SPORTASSIST_ETC, update_env_keys

RUN_IP = Path("/run/sportassist/camera.ip")

CLEAR_KEYS = {
    "CAMERA_HOSTNAME": "",
    "CAMERA_IP": "",
    "CAMERA_DEVICE_ID": "",
    "CAMERA_REPORTED_NAME": "",
    "CAMERA_ASSIGNED": "0",
    "CAMERA_USERNAME": "",
    "CAMERA_PASSWORD": "",
    "CAMERA_RTSP_PATH": "",
    "INGEST_WIDTH": "",
    "INGEST_HEIGHT": "",
    "INGEST_FPS": "",
    "INGEST_CODEC": "ultra265",
    "INGEST_BITRATE": "",
    "INGEST_GOP": "25",
    "CAMERA_STREAM_LABEL": "",
    "INGEST_FALLBACK_STEP": "",
    "CAMERA_RTSP_PATH_SUB": "",
}


def clear_camera_config(*, stop_ingest: bool = True) -> None:
    update_env_keys(SPORTASSIST_ETC / "camera.env", CLEAR_KEYS)
    if RUN_IP.is_file():
        RUN_IP.unlink(missing_ok=True)
    if stop_ingest:
        stop_replay_buffer()
        clear_hls_buffers()


def main() -> int:
    clear_camera_config(stop_ingest=True)
    print('{"ok": true}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
