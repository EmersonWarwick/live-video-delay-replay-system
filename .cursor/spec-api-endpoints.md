# Spec: HTTP API and HLS Endpoints

Normative specification for endpoints the Raspberry Pi serves to **mobile clients** (Android Kotlin, iOS Swift planned) and optional browser clients.

Related: `.cursor/spec-mobile-clients.md`, `.cursor/spec-hls-replay-buffer.md`, `.cursor/spec-android-app.md`, `.cursor/architecture-and-technical-spec.md`.

---

## 1. Purpose

Define the **only** production URLs clients use for replay (plus optional live/status/control).

**Base host**: `192.168.4.1` (Pi Wi‑Fi AP)  
**Default port**: `8080` (Flask `ldrs-web` serves HTTP + static HLS)

**Authentication:** all endpoints except **`GET /device-info`** and login routes require a web session — see `.cursor/spec-settings-page.md` §3.

---

## 2. HLS Replay Endpoints (Required)

### 2.1 Playlist (1080p Wi‑Fi tier)

```http
GET /hls/live.m3u8
```

- Serves **1920×1080** fMP4 HLS from `/var/lib/sportassist/hls/`.
- When delayed mode is active and `delayed_sync.m3u8` is fresh: serves trimmed sliding playlist (~delay window) at the **delayed live edge**.
- Otherwise serves rolling `live.m3u8` at the HLS live edge.
- **Live tab** in mobile apps — not for full 20 min scrub.
- **Must not** point to 4K buffer (`hls-4k/`).

```http
GET /hls/buffer.m3u8
```

- Full rolling **20-minute** `live.m3u8` (no delayed trim) — **Review tab** / coach scrub.

```http
GET /api/review
```

**Response** (`application/json`) — timeline for Review tab:

```json
{
  "ok": true,
  "cameraConnected": true,
  "bufferHealth": "ok",
  "bufferWarming": false,
  "bufferDurationSeconds": 1200,
  "segmentDurationSeconds": 1.0,
  "liveDelaySeconds": 20,
  "playbackOffsetSeconds": 17,
  "oldestTime": "2026-06-28T07:10:00.000Z",
  "latestTime": "2026-06-28T07:30:00.000Z",
  "liveEdgeTime": "2026-06-28T07:29:43.000Z",
  "livePlaylist": "/hls/live.m3u8",
  "reviewPlaylist": "/hls/buffer.m3u8",
  "wifiBuffer": { "width": 1920, "height": 1080, "diskBytes": 800000000 },
  "delayedSyncReady": true
}
```

| Field            | Purpose                                           |
| ---------------- | ------------------------------------------------- |
| `oldestTime`     | Earliest scrub position (buffer start)            |
| `latestTime`     | Ingest live edge (newest segment)                 |
| `liveEdgeTime`   | Delayed live edge — **Go to delayed live** target |
| `livePlaylist`   | Live tab HLS URL                                  |
| `reviewPlaylist` | Review tab HLS URL (`/hls/buffer.m3u8`)           |

Clients stream segments on demand; do not download the full buffer as one file.

```http
GET /replay
```

- Browser replay page (hls.js + `/hls/buffer.m3u8`). **Requires web session.**
- `GET /review` redirects to `/replay` (legacy).

```http
GET /hls/sync.m3u8
GET /hls/delayed.m3u8
```

- Aliases to `delayed_sync.m3u8` when available.

### 2.2 Media segments

```http
GET /hls/{segment}
```

Examples:

- `GET /hls/seg_1710000000123.m4s`
- `GET /hls/init.mp4` (initialization segment if used)

- **Content-Type**: `video/mp4` or appropriate fMP4 fragment type.
- Served from `/var/lib/sportassist/hls/` (read-only, cache headers allowed).
- Return **404** for pruned segments (client must recover).

### 2.3 CORS (required)

All HTTP responses include CORS headers for browser and hybrid app clients:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

`OPTIONS` preflight is supported on `/api/*` and `/settings/*`. Native Android ExoPlayer / iOS AVPlayer do not require CORS; browsers and WebViews may.

---

## 3. Status Endpoint (Recommended)

```http
GET /api/status
```

**Response** (`application/json`):

```json
{
  "cameraConnected": true,
  "bufferHealth": "ok",
  "bufferWarming": false,
  "liveDelaySeconds": 14,
  "pipelineLatencySeconds": 3,
  "playbackOffsetSeconds": 11,
  "hdmiDelaySeconds": 14,
  "delayedHdmiReady": true,
  "delayedSyncReady": true,
  "hlsDelayUpdaterActive": true,
  "replayUsingDelayedPlaylist": true,
  "hdmiEnabled": true,
  "hdmiOutputMode": "delayed",
  "bufferDurationSeconds": 1200,
  "oldestSegmentTime": "2026-06-23T10:05:00.000Z",
  "latestSegmentTime": "2026-06-23T10:25:00.000Z",
  "safeDelayEdgeTime": "2026-06-23T10:24:46.000Z",
  "segmentDurationSeconds": 1.0,
  "activeClients": 2
}
```

| Field                                   | Purpose                                                                                   |
| --------------------------------------- | ----------------------------------------------------------------------------------------- |
| `cameraConnected`                       | RTSP ingest healthy                                                                       |
| `bufferHealth`                          | `ok` \| `warming` \| `focus` \| `stalled` \| `error` — `focus` when Show Live HDMI active |
| `bufferWarming`                         | true until Wi‑Fi delayed playlist and/or ring ready                                       |
| `liveDelaySeconds`                      | User delay setting (`LIVE_DELAY_SECONDS`)                                                 |
| `pipelineLatencySeconds`                | Camera→HLS-edge latency (Wi‑Fi offset math)                                               |
| `playbackOffsetSeconds`                 | Wi‑Fi HLS seconds behind HLS edge                                                         |
| `hdmiDelaySeconds`                      | Effective HDMI wall-clock delay                                                           |
| `delayedHdmiReady` / `delayedSyncReady` | HDMI / Wi‑Fi delayed playlists ready for playback                                         |
| `hlsDelayUpdaterActive`                 | `ldrs-hls-delay-playlists.service` active                                                 |
| `replayUsingDelayedPlaylist`            | `/hls/live.m3u8` serving delayed Wi‑Fi playlist                                           |
| `hdmiEnabled`                           | HDMI service enabled (`HDMI_ENABLED`)                                                     |
| `hdmiOutputMode`                        | `delayed` \| `live` — `live` = Show Live (no replay ingest)                               |
| `hdmiFocusMode`                         | true when `hdmiOutputMode=live` and HDMI on                                               |
| `hdmiActiveService`                     | `live` \| `delayed` \| `off` — which HDMI unit is running                                 |
| `bufferDurationSeconds`                 | Rolling window (1200)                                                                     |
| `oldestSegmentTime`                     | Scrub lower bound                                                                         |
| `latestSegmentTime`                     | Ingest live edge                                                                          |
| `safeDelayEdgeTime`                     | Scrub upper bound (= latest − Wi‑Fi offset)                                               |

Android uses this for timeline bounds and default start position. The future iOS app uses the same fields.

---

## 4. Lens presets

Recall-only pool-deck presets. Save/rename/delete in Settings — `spec-settings-page.md` §11.

```http
GET /presets
```

- HTML button page (`presets.html`).

```http
POST /presets/recall
Content-Type: application/json

{ "id": "wide" }
```

**Response** (`application/json`):

```json
{ "ok": true }
```

| Field | Purpose                                                                     |
| ----- | --------------------------------------------------------------------------- |
| `id`  | Preset slug from `lens-presets.json` (same ids shown on `/presets` buttons) |

Errors return `{ "ok": false, "error": "..." }` with HTTP 400.

---

## 5. Device identification (public)

Called once at app startup (and after AP reconnect).

```http
GET /device-info
```

**Response** (`application/json`):

```json
{
  "device": "LDRS2",
  "status": "OK"
}
```

| Field    | Purpose                                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `device` | Appliance generation — **`LDRS2`** = v2 Pi replay (Live `/hls/live.m3u8`, Review `/hls/buffer.m3u8`, `GET /api/review`, Presets `/presets`) |
| `status` | `OK` when the Pi web service is running and identifies as LDRS2                                                                             |

**Mobile apps:** `GET /device-info` before login; tab map: `spec-mobile-clients.md` §2.

---

## 6. Camera discovery and configuration

Used when **customer LAN** mode (`ETH_CAMERA_DHCP=0`) — see `.cursor/spec-camera-discovery.md`.

### 4.1 Search customer network

```http
POST /api/camera/discover
```

**Response** (`application/json`):

```json
{
  "searching": false,
  "cameras": [
    {
      "hostname": "SportAssist-ABC123456",
      "ip": "192.168.1.42",
      "onvif": true,
      "rtspPort": 554
    }
  ],
  "error": null
}
```

- Pi runs `ldrs-discover-cameras.sh` on **Ethernet** (`eth0`).
- Only devices matching configured **hostname rules** (`SportAssist-*`, `sport-assist-*`) are returned.
- May take up to **30 s**; UI should poll or use async response.

### 4.2 Read current camera (no password)

```http
GET /api/camera
```

```json
{
  "hostname": "SportAssist-ABC123456",
  "ip": "192.168.1.42",
  "username": "admin",
  "rtspPort": 554,
  "rtspPath": "/Streaming/Channels/101",
  "ingestWidth": 3840,
  "ingestHeight": 2160,
  "ingestFps": 25,
  "ingestCodec": "ultra265",
  "ingestGop": 25,
  "ingestBitrate": 12000000,
  "fallbackStep": 1,
  "streamLabel": "Main stream",
  "subStream": {
    "rtspPath": "/Streaming/Channels/102",
    "width": 1920,
    "height": 1080,
    "fps": 25,
    "codec": "h264",
    "gop": 25
  },
  "configured": true
}
```

**Never** include `password` in response.

### 4.3 Assign camera (commissioning)

```http
POST /api/camera/assign
Content-Type: application/json

{
  "ip": "192.168.1.42",
  "currentUsername": "admin",
  "currentPassword": "YOUR-PRIVATE-ADMIN-PASSWORD",
  "rtspPort": 554,
  "onvifPort": 80
}
```

On success, Pi invokes `ldrs-assign-camera.sh`:

1. ONVIF `CreateUsers` / `SetUser` → username **`sportassist`**, random password
2. Hostname **`SportAssistCam`** (fixed)
3. ONVIF `GetDeviceInformation` → `CAMERA_DEVICE_ID`, `CAMERA_REPORTED_NAME`
4. `configure_streams.py` — fallback ladder + `camera.env` (`CAMERA_ASSIGNED=1`)

**Response** (success):

```json
{
  "ok": true,
  "assigned": true,
  "hostname": "SportAssistCam",
  "deviceId": "210235C62512345678",
  "reportedName": "IPC3638SB-S-AL2 (210235C62512345678)",
  "username": "sportassist",
  "password": "aB3xK9mN2pQ7",
  "cameraConnected": true,
  "configured": true,
  "fallbackStep": 1,
  "main": {
    "width": 3840,
    "height": 2160,
    "fps": 25,
    "codec": "h265",
    "gop": 25
  }
}
```

Settings page reload shows assigned hostname, `sportassist`, and password (plain text). **`GET /api/camera` still omits password.**

### 4.4 Save camera credentials (legacy)

```http
POST /api/camera
Content-Type: application/json

{
  "hostname": "SportAssist-ABC123456",
  "ip": "192.168.1.42",
  "username": "admin",
  "password": "secret",
  "rtspPort": 554
}
```

On success, Pi invokes `ldrs-set-camera-config.sh` then `ldrs-configure-camera-streams.sh` if streams not yet configured.

Optional body fields for **advanced manual override** only: `rtspPath`, `ingestWidth`, `ingestHeight`, `ingestFps`, `ingestCodec`, `ingestGop` — must pass ffprobe validation.

**Response** (success):

```json
{
  "ok": true,
  "cameraConnected": true,
  "configured": true,
  "fallbackStep": 1,
  "main": {
    "width": 3840,
    "height": 2160,
    "fps": 25,
    "codec": "h265",
    "gop": 25
  }
}
```

**Response** (RTSP auth failure):

```json
{ "ok": false, "error": "authentication_failed" }
```

Invokes `ldrs-set-camera-config.sh` and `ldrs-configure-camera-streams.sh`; persists `/etc/sportassist/camera.env`; restarts replay buffer.

### 4.5 Configure camera streams (ONVIF interrogate + apply)

```http
POST /api/camera/streams
Content-Type: application/json

{
  "hostname": "SportAssist-ABC123456",
  "ip": "192.168.1.42",
  "username": "admin",
  "password": "secret",
  "rtspPort": 554,
  "reconfigure": false
}
```

**Response** (success):

```json
{
  "configured": true,
  "fallbackStep": 1,
  "capabilities": {
    "resolutions": ["3840x2160", "2560x1440", "1920x1080"],
    "supportedCodecs": [
      { "id": "ultra265", "label": "Ultra 265", "eligible": true },
      { "id": "h265", "label": "H.265", "eligible": true },
      { "id": "h264", "label": "H.264", "eligible": true },
      { "id": "mjpeg", "label": "MJPEG", "eligible": false }
    ],
    "bitrateRange": { "min": 1000000, "max": 16000000 }
  },
  "main": {
    "width": 3840,
    "height": 2160,
    "fps": 25,
    "codec": "ultra265",
    "gop": 25,
    "bitrate": 12000000,
    "rtspPath": "/Streaming/Channels/101",
    "label": "Main stream"
  },
  "sub": {
    "width": 1920,
    "height": 1080,
    "fps": 25,
    "codec": "h264",
    "gop": 25,
    "bitrate": 5000000,
    "rtspPath": "/Streaming/Channels/102",
    "label": "Sub stream"
  },
  "error": null
}
```

- Pi runs `ldrs-configure-camera-streams.sh` on **Ethernet**.
- Uses **ONVIF Media Service** to read capabilities and **SetVideoEncoderConfiguration** to apply profile.
- Walks fallback ladder; selects best codec (Ultra 265 → H.265 → H.264; never MJPEG).
- See `spec-camera-stream-profiles.md`.

---

## 7. Out of scope — WebRTC and `/api/mode`

**Not required in v2.** Do not implement:

- `POST /api/mode`
- `/live/webrtc-*` or MediaMTX `:8889`
- Any WebRTC or low-latency Wi‑Fi live path for coaches

| Need                              | Use instead                                                              |
| --------------------------------- | ------------------------------------------------------------------------ |
| Coach near-live pool view         | **HDMI 4K delayed** — `HDMI_OUTPUT_MODE=delayed` (`spec-hdmi-output.md`) |
| Camera lens / focus on HDMI       | **HDMI live focus** — `HDMI_OUTPUT_MODE=live` (stops replay buffer)      |
| Coach lens / HDMI / delay control | **Settings** on mobile (`/settings`)                                     |

Mobile apps use **delayed HLS only** (`GET /hls/live.m3u8`). HDMI mode does not change mobile playback.

---

## 8. Endpoints explicitly NOT on mobile path

| Endpoint               | Where it lives                        |
| ---------------------- | ------------------------------------- |
| Camera RTSP `rtsp://…` | Pi ingest only — never shipped to app |
| ONVIF                  | Pi `/settings` / helpers only         |
| Camera credentials     | `/etc/sportassist/camera.env` only    |

---

## 9. Legacy / deprecated client URLs

Do **not** use as primary v2 replay:

| URL                                       | Status                                            |
| ----------------------------------------- | ------------------------------------------------- |
| `http://192.168.4.1:8888/live/index.m3u8` | MediaMTX short HLS — deprecated                   |
| `http://192.168.4.1:8889/*` WebRTC live   | **Not in v2** — use HDMI 4K                       |
| Direct RTSP on tablet                     | **Forbidden** in production                       |
| Browser replay at `/replay`               | **Requires web login** — secondary to native apps |
| Unauthenticated HLS on Wi‑Fi AP           | **Not in v2** — web session required              |

---

## 10. Implementation notes

- Flask may serve `/hls/*` via `send_from_directory` with correct MIME types, or nginx may alias `/var/lib/sportassist/hls/`.
- Playlist must not embed absolute camera URLs.
- Rate-limit not required on LAN AP; log anomalous request volumes.

---

## 11. Acceptance criteria

API and mobile client behaviour: `spec-mobile-clients.md` §4, `spec-api-endpoints.md` §11 (camera endpoints below).

3. `POST /api/camera/assign` provisions camera and ONVIF streams; `GET /api/camera` never returns password.
4. `POST /api/camera/streams` applies fallback ladder.
5. `/api/status` reflects buffer times and `ingestFallbackStep`.
6. Multiple clients fetch same HLS segments without server-side duplication.
