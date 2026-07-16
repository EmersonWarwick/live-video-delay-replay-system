# Spec: RTSP Ingest from IP Camera

Normative specification for Pi-side RTSP ingest — driven by **ONVIF-configured stream profiles** in `camera.env`.

Related: `.cursor/spec-camera-stream-profiles.md`, `.cursor/spec-hls-replay-buffer.md`, `.cursor/architecture-and-technical-spec.md`.

---

## 1. Purpose

The Raspberry Pi connects to the camera using **main** (and when applicable **sub**) RTSP URIs that the Pi has **programmed via ONVIF** and validated with ffprobe. That feed powers **`ldrs-replay-buffer`**.

**Production clients never use the RTSP URL.**

The Pi **remuxes** camera bitstreams into fMP4 HLS. It does **not** decode/re-encode except when documented as an exception (see `spec-camera-stream-profiles.md` §1).

---

## 2. Architecture

```text
IP Camera
    │  Pi ONVIF: interrogate → choose ladder step → SetVideoEncoderConfiguration
    │  Main RTSP  (Pi only, TCP)
    │  Sub RTSP   (1080p when main > 1080p)
    ▼
ldrs-replay-buffer (ffmpeg -c:v copy)
    │  dual fMP4 HLS (HDMI main; Wi‑Fi sub or main)
    ▼
GET /hls/live.m3u8  →  Android
```

---

## 3. Configuration — `/etc/sportassist/camera.env`

| Key                                                           | Purpose                                                    |
| ------------------------------------------------------------- | ---------------------------------------------------------- |
| `CAMERA_HOSTNAME`, `CAMERA_IP`, `CAMERA_RTSP_PORT`            | Connection                                                 |
| `CAMERA_USERNAME`, `CAMERA_PASSWORD`                          | Auth                                                       |
| `CAMERA_RTSP_PATH`                                            | Main stream path (ONVIF-configured)                        |
| `CAMERA_RTSP_PATH_SUB`                                        | Sub stream for Wi‑Fi when main > 1080p                     |
| `INGEST_WIDTH`, `INGEST_HEIGHT`, `INGEST_FPS`, `INGEST_CODEC` | Main encoder settings (`ultra265`, `h265`, `h264`)         |
| `INGEST_GOP`, `INGEST_BITRATE`                                | Keyframe interval and bitrate used when programming camera |
| `INGEST_SUB_*`                                                | Sub stream settings                                        |
| `INGEST_FALLBACK_STEP`                                        | Which ladder step (1–4) succeeded                          |
| `CAMERA_RTSP_TRANSPORT`                                       | `tcp`                                                      |

**Single source of truth** — `ldrs-replay-buffer.sh` reads URIs and dimensions from here.

Runtime IP fallback: `/run/sportassist/camera.ip`.

---

## 4. ffmpeg Ingest (Behavioural)

`ldrs-replay-buffer.sh` must:

1. Build RTSP URLs from `camera.env` + resolved IP (main + sub if `CAMERA_RTSP_PATH_SUB` set).
2. Connect with `-rtsp_transport tcp`.
3. Verify streams match stored `INGEST_*` / `INGEST_SUB_*` (log warning if camera drifted).
4. **Remux only** (`-c:v copy`) to fMP4 HLS on both branches — see `spec-hls-replay-buffer.md`.
5. Exit non-zero if fps sustained below 25, GOP unsuitable for 1 s segments, or RTSP fails.
6. **Never** scale or re-encode in production unless exception documented in `spec-camera-stream-profiles.md` §1.

---

## 5. Configuration and Re-Configuration

Triggered by:

- First `POST /api/camera` save → `ldrs-configure-camera-streams.sh`
- **Configure camera streams** in settings → `POST /api/camera/streams`
- Boot: if `camera.env` incomplete, wait for operator; if complete, ffprobe validate before ingest

---

## 6. Security

- Credentials and RTSP paths only in `camera.env` (mode `640`).
- Never log RTSP URL with password.
- Never expose full RTSP URL to Android API.

---

## 7. Acceptance Criteria

1. Ingest uses ONVIF-configured `CAMERA_RTSP_PATH` (+ sub if set) after reboot.
2. Pi remuxes camera output; no Pi transcode in default product path.
3. ffprobe confirms ≥ 25 fps and keyframe interval before persisting configuration.
4. HDMI buffer matches main ingest resolution; Wi‑Fi buffer is 1080p via sub stream or 1080p main.
