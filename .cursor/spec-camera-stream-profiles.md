# Spec: Camera Stream Configuration via ONVIF

Normative specification for **interrogating** the IP camera over ONVIF Media Service, **choosing a known-good profile** using a defined fallback ladder, **programming the camera encoder**, and persisting the result on the Pi for RTSP ingest.

Related: `.cursor/spec-settings-page.md`, `.cursor/spec-camera-discovery.md`, `.cursor/spec-rtsp-ingest.md`, `.cursor/spec-video-resolution.md`, `.cursor/spec-hls-replay-buffer.md`.

---

## 1. Design Principle — Remux, Do Not Transcode

On Raspberry Pi 5 the preferred pipeline is:

```text
Camera encodes correct codec, resolution, frame rate, GOP
    → Pi reads RTSP
    → Pi remuxes into fMP4 HLS (copy bitstream)
    → Pi does NOT decode/re-encode unless absolutely necessary
```

**The Pi must program the camera** to output the desired stream via ONVIF — not guess RTSP paths or accept whatever the camera happens to be sending.

Transcoding on the Pi (scale, H.264 re-encode) is **forbidden in production** unless:

1. Camera cannot be configured to the required profile via ONVIF, **and**
2. Soak test documents Pi 5 cannot sustain remux-only at chosen tier, **and**
3. Exception is recorded in commissioning notes.

When main ingest exceeds 1080p, configure a **camera sub stream** at 1080p for the Wi‑Fi buffer so both outputs remain remux-only.

---

## 2. User Story

After camera credentials are available (discovery or direct mode):

1. Pi **interrogates** the camera via ONVIF Media Service (Ethernet only).
2. Pi reads capabilities and existing profiles (main + sub).
3. Pi **selects and applies** a known-good profile using the fallback ladder (§4).
4. Pi validates with ffprobe; persists settings to `camera.env`.
5. Settings UI shows the **configured profile** (resolution, fps, codec, GOP, bitrate) — operator may **Re-configure** or optionally override in advanced mode.
6. `ldrs-replay-buffer` ingests using stored RTSP URIs after save/reboot.

Android never talks to the camera or ONVIF.

---

## 3. ONVIF Media Service Interrogation

Primary method: **ONVIF Media Service** (not ffprobe-first guessing).

### 3.1 Read from camera

| Data                     | ONVIF / method                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------- |
| Supported resolutions    | `GetVideoEncoderConfigurations`, `GetVideoEncoderConfigurationOptions`                               |
| Supported frame rates    | Encoder options per resolution                                                                       |
| Codec options            | `GetVideoEncoderConfigurationOptions` → `Encoding` / `EncodingTypesAvailable` per profile (see §3.3) |
| Bitrate range            | Min/max from encoder options                                                                         |
| Existing RTSP profiles   | `GetProfiles` + `GetStreamUri` (main + sub)                                                          |
| Main vs sub stream       | Profile tokens / `VideoSourceConfiguration` linkage                                                  |
| Current encoder settings | `GetVideoEncoderConfiguration` (resolution, fps, codec, bitrate, GOP)                                |

Supplement with **ffprobe** on `GetStreamUri` results to confirm actual output after configuration — not as the primary discovery mechanism.

### 3.3 Codec discovery (Ultra 265, H.265, H.264, MJPEG)

Via the settings flow, the Pi reads **supported video encodings** from ONVIF Media Service before choosing a profile.

#### 3.3.1 Standard ONVIF (all cameras)

From `GetVideoEncoderConfigurationOptions` on each profile token (main + sub):

| ONVIF `Encoding` / option | Product ID | Replay eligible         |
| ------------------------- | ---------- | ----------------------- |
| `H264`                    | `h264`     | **Yes**                 |
| `H265` / `HEVC`           | `h265`     | **Yes**                 |
| `JPEG` / `MJPEG`          | `mjpeg`    | **No** — display only   |
| `MPEG4`                   | `mpeg4`    | **No** — not used in v2 |

Expose in settings/API as:

```json
"supportedCodecs": [
  { "id": "ultra265", "label": "Ultra 265", "eligible": true },
  { "id": "h265", "label": "H.265", "eligible": true },
  { "id": "h264", "label": "H.264", "eligible": true },
  { "id": "mjpeg", "label": "MJPEG", "eligible": false }
]
```

Only codecs with `"eligible": true` may be auto-selected for replay ingest.

#### 3.3.2 UNV Ultra 265 (preferred camera: IPC3638SB)

**Ultra 265** is UNV’s H.265-based smart codec. Detection order:

1. `GetDeviceInformation` → manufacturer contains `UNV` / `Uniview`.
2. Query UNV ONVIF extension or `GetVideoEncoderConfigurationOptions` extended enum if the camera exposes **`Ultra265`**, **`U-Code`**, or vendor-specific encoding token (firmware-dependent).
3. If Ultra 265 cannot be distinguished from H.265 in ONVIF but the camera web UI / datasheet confirms support, treat **`h265` at 4K/1440p on UNV** as Ultra 265 candidate: attempt UNV-specific `SetVideoEncoderConfiguration` encoding value first; ffprobe must report `hevc`.

**Stored value**: `INGEST_CODEC=ultra265` when Ultra 265 mode is applied; `h265` when standard H.265 is used.

**Remux**: ffmpeg `-c:v copy` — Ultra 265 bitstreams are HEVC; no Pi decode.

#### 3.3.3 MJPEG — never auto-selected

MJPEG may appear in ONVIF capabilities. The settings screen **lists** it under “Supported encodings (informational)” but the Pi **never** selects MJPEG for replay:

- Bandwidth too high at 4K/1440p for 20-minute buffer and Ethernet budget.
- Poor fit for fMP4 HLS segment boundaries and poolside scrubbing.
- If MJPEG is the only option offered, configure fails with a clear error.

#### 3.3.4 Codec selection priority (main stream)

At each resolution tier in the fallback ladder (§4), try codecs **in order**:

| Priority | Codec         | Notes                                        |
| -------- | ------------- | -------------------------------------------- |
| **1**    | **Ultra 265** | Best compression; UNV and compatible cameras |
| **2**    | **H.265**     | Standard HEVC when Ultra 265 unavailable     |
| **3**    | **H.264**     | Widest compatibility; required fallback      |
| —        | MJPEG         | **Never** for replay                         |

**Sub stream** (Wi‑Fi, when main > 1080p): always **H.264** @ 1080p — independent of main codec — for Android ExoPlayer reliability.

After selection: apply via ONVIF, ffprobe confirm codec string (`hevc` / `h264`), persist `INGEST_CODEC` / `INGEST_SUB_CODEC` in `camera.env`.

### 3.4 Configure camera (write)

After selecting target profile, Pi applies settings via ONVIF:

| Setting                 | Target                                                |
| ----------------------- | ----------------------------------------------------- |
| Resolution              | Per fallback ladder (§4)                              |
| Frame rate              | **25 fps** (or 30 fps only at 1080p fallback step)    |
| Codec                   | Best eligible codec from §3.3.4 at this resolution    |
| Bitrate                 | Fixed or **capped VBR** within camera-supported range |
| GOP / keyframe interval | **25 frames** (= 1 keyframe per second at 25 fps)     |

Use `SetVideoEncoderConfiguration` (and related profile linkage) on the **main stream** profile token.

When main resolution > 1080p, also configure **sub stream**:

| Sub stream | Value                                                  |
| ---------- | ------------------------------------------------------ |
| Resolution | 1920 × 1080                                            |
| Frame rate | 25 fps                                                 |
| Codec      | **H.264** (Android ExoPlayer reliability on Wi‑Fi HLS) |
| Bitrate    | Capped VBR ~5 Mbps                                     |
| GOP        | 25 frames                                              |

Re-read `GetStreamUri` for main and sub after apply; ffprobe both before persisting.

---

## 4. Profile Selection — Fallback Ladder

Pi walks **resolution tiers**; at each tier tries **codec priority** (Ultra 265 → H.265 → H.264). MJPEG is skipped. Each attempt must pass ffprobe (≥ 25 fps, GOP ≈ 25 frames, remux-compatible bitstream).

### 4.1 Resolution × codec attempts (in order)

| Attempt | Resolution  | FPS               | Codec try order                    |
| ------- | ----------- | ----------------- | ---------------------------------- |
| **1a**  | 3840 × 2160 | 25                | Ultra 265 → H.265 → H.264          |
| **1b**  | 3840 × 2160 | 25                | (next codec in 1a if prior failed) |
| **2**   | 2560 × 1440 | 25                | Ultra 265 → H.265 → H.264          |
| **3**   | 1920 × 1080 | 25 (prefer) or 30 | H.264 → H.265 → Ultra 265          |

Stop at first success. Store `INGEST_FALLBACK_STEP` (1–4) and `INGEST_CODEC` (`ultra265`, `h265`, or `h264`).

**Commercial starting point**: attempt **3840×2160 @ 25 fps Ultra 265** on UNV IPC3638SB before wider ladder.

### 4.2 Validation per attempt

1. ONVIF encoder options include resolution + codec.
2. `SetVideoEncoderConfiguration` applies codec, bitrate, GOP 25.
3. ffprobe main URI — width, height, fps ≥ 25, codec matches, IDR interval ≤ 1 s.
4. Brief stability check (~10 s RTSP read).
5. If fail → next codec or next resolution; log reason.

### 4.3 Sub stream (when main > 1080p)

After main succeeds, configure sub: **1920×1080 @ 25 fps H.264**, GOP 25, ~5 Mbps capped VBR. ffprobe validate independently.

---

## 5. Commercial Encoder Defaults

Applied when programming camera (main stream unless step 4):

| Parameter               | Value                                                                                              |
| ----------------------- | -------------------------------------------------------------------------------------------------- |
| Resolution              | 2560×1440 or 3840×2160 (per ladder step)                                                           |
| Frame rate              | **25 fps**                                                                                         |
| Codec                   | Best from ladder: **Ultra 265** preferred, else H.265, else H.264                                  |
| Bitrate                 | Fixed or capped VBR (use camera max suitable for tier — ~12 Mbps 4K, ~8 Mbps 1440p, ~5 Mbps 1080p) |
| GOP / keyframe interval | **25 frames** (1 s at 25 fps)                                                                      |
| HLS segment length (Pi) | **1 s** (`HLS_SEGMENT_DURATION=1`)                                                                 |
| Buffer duration         | **20 min** (`BUFFER_DURATION_SECONDS=1200`)                                                        |
| Playback delay          | **14 s** default (`LIVE_DELAY_SECONDS=14`)                                                         |

**GOP is critical for scrubbing** — frequent keyframes enable clean segment boundaries and responsive timeline drag. Target **one IDR per second** minimum.

---

## 6. Downstream Pipeline (Remux-Only)

```text
ONVIF-configured camera
    ├── Main RTSP  → ldrs-replay-buffer → fMP4 HLS /var/lib/sportassist/hls-4k/  (HDMI)
    └── Sub RTSP   → ldrs-replay-buffer → fMP4 HLS /var/lib/sportassist/hls/     (Wi‑Fi, 1080p)
```

If main is already ≤ 1080p (step 4), **single RTSP** feeds both buffers via remux (same URI; two `-c:v copy` outputs).

| Ladder step         | HDMI buffer | Wi‑Fi buffer      | Pi transcode |
| ------------------- | ----------- | ----------------- | ------------ |
| 1–3 (4K/1440p main) | Remux main  | Remux sub @ 1080p | **None**     |
| 4 (1080p main)      | Remux main  | Remux main        | **None**     |

---

## 7. Persistence — `/etc/sportassist/camera.env`

```bash
# Connection
CAMERA_HOSTNAME=SportAssist-ABC123456
CAMERA_IP=192.168.1.42
CAMERA_RTSP_PORT=554
CAMERA_RTSP_TRANSPORT=tcp
CAMERA_USERNAME=admin
CAMERA_PASSWORD=secret

# Main stream (HDMI ingest) — Pi-configured via ONVIF
CAMERA_RTSP_PATH=/Streaming/Channels/101
INGEST_WIDTH=3840
INGEST_HEIGHT=2160
INGEST_FPS=25
INGEST_CODEC=ultra265
INGEST_BITRATE=12000000
INGEST_GOP=25
CAMERA_STREAM_LABEL=Main stream
INGEST_FALLBACK_STEP=1

# Sub stream (Wi‑Fi ingest) — when main > 1080p
CAMERA_RTSP_PATH_SUB=/Streaming/Channels/102
INGEST_SUB_WIDTH=1920
INGEST_SUB_HEIGHT=1080
INGEST_SUB_FPS=25
INGEST_SUB_CODEC=h264
INGEST_SUB_BITRATE=5000000
INGEST_SUB_GOP=25
```

| Key                                                 | Required         | Notes                                      |
| --------------------------------------------------- | ---------------- | ------------------------------------------ |
| `CAMERA_RTSP_PATH`                                  | yes              | Main stream URI path after ONVIF configure |
| `CAMERA_RTSP_PATH_SUB`                              | when main >1080p | Sub stream for Wi‑Fi remux                 |
| `INGEST_CODEC`                                      | yes              | `ultra265`, `h265`, or `h264`              |
| `INGEST_WIDTH`, `INGEST_HEIGHT`, `INGEST_FPS`, etc. | yes              | Main encoder settings applied via ONVIF    |
| `INGEST_GOP`                                        | yes              | Keyframe interval in frames (25)           |
| `INGEST_BITRATE`                                    | yes              | bps target used when programming camera    |
| `INGEST_FALLBACK_STEP`                              | yes              | 1–4 — which ladder step succeeded          |
| `INGEST_SUB_*`                                      | when sub used    | Sub stream settings                        |

---

## 8. Settings UI

Section: **Camera stream (auto-configured)**

| Control                          | Behaviour                                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------- |
| **Configure camera streams**     | `POST /api/camera/streams` — runs ONVIF interrogate + ladder + apply                      |
| **Supported codecs**             | Read-only from ONVIF: Ultra 265, H.265, H.264, MJPEG — MJPEG greyed “not used for replay” |
| **Status**                       | Shows configured main/sub: `{width}×{height} @ {fps} fps {codec label}, GOP {gop}`        |
| **Fallback step**                | e.g. “Step 1: 4K Ultra 265” or “Step 2: 4K H.264”                                         |
| **Re-configure**                 | Re-run ladder from step 1 (e.g. after camera firmware change)                             |
| **Advanced override** (optional) | Manual profile pick from interrogated capabilities — must still pass ffprobe + GOP check  |

Default flow: operator saves credentials → Pi **auto-configures** on first save (no manual stream pick required).

Hint: “The Raspberry Pi reads supported codecs (Ultra 265, H.265, H.264, MJPEG) via ONVIF, selects the best for replay, and stores your choice on the Pi. MJPEG is not used for replay.”

Errors:

- ONVIF auth failure → check username/password
- No valid profile after step 4 → “Camera could not be configured for replay. Check ONVIF and encoding support.”
- GOP not configurable → warn; ffprobe must still show IDR ≤ 1 s

---

## 9. Helpers

### `ldrs-probe-camera-streams.sh`

Read-only interrogation for UI/API — returns ONVIF capabilities including **`supportedCodecs`** (§3.3) + current profiles (JSON). Does not modify camera.

### `ldrs-configure-camera-streams.sh`

1. ONVIF read capabilities (§3.1)
2. Walk fallback ladder (§4)
3. Apply encoder settings (§3.2)
4. ffprobe validate main (+ sub if applicable)
5. Write `camera.env` ingest fields
6. Restart `ldrs-replay-buffer.service`

Invoked by `POST /api/camera/streams` (configure mode) and on first `POST /api/camera` save when stream not yet configured.

**Sudoers**:

```text
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-probe-camera-streams.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-configure-camera-streams.sh
```

---

## 10. API

See `.cursor/spec-api-endpoints.md` §4.4 `POST /api/camera/streams`.

Response includes: `configured`, `fallbackStep`, `main`, `sub`, `capabilities.supportedCodecs`, `error`.

---

## 11. Acceptance Criteria

1. Pi reads **Ultra 265, H.265, H.264, MJPEG** support via ONVIF before ingest.
2. Pi selects **best eligible codec** (Ultra 265 → H.265 → H.264); **never MJPEG** for replay.
3. Pi **programs** camera encoder; stores `INGEST_CODEC` in `camera.env`; remuxes on ingest.
4. Settings shows supported codecs and configured choice.
5. Main + sub streams configured so Pi **remuxes only** for HDMI and Wi‑Fi buffers.
6. GOP **25 frames** at 25 fps unless camera cannot comply (document exception).
7. Profile persists across reboot; ffprobe confirms ≥ 25 fps and 1 s keyframe alignment.
