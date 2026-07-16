# Spec: Rolling HLS/fMP4 Replay Buffer (Raspberry Pi 5)

Normative specification for Pi-owned **dual-tier** rolling buffers — **remux-only** from camera-configured RTSP streams.

Related: `.cursor/spec-video-resolution.md`, `.cursor/spec-camera-stream-profiles.md`, `.cursor/NetworkCameraSpec.md`, `.cursor/spec-api-endpoints.md`, `.cursor/spec-hdmi-output.md`.

---

## 1. Purpose

The Pi maintains **two rolling HLS buffers** on disk from camera RTSP:

| Buffer               | Path                           | Source                                    | Resolution             | Served to                                               |
| -------------------- | ------------------------------ | ----------------------------------------- | ---------------------- | ------------------------------------------------------- |
| **Tier A (4K disk)** | `/var/lib/sportassist/hls-4k/` | Camera **main** stream                    | Native main (up to 4K) | HDMI delayed playback (local); not served over Wi‑Fi AP |
| **Tier B (Wi‑Fi)**   | `/var/lib/sportassist/hls/`    | Camera **sub** stream (or main if ≤1080p) | **1920×1080**          | `GET /hls/live.m3u8`, `GET /hls/buffer.m3u8`            |

Both HLS tiers retain **20 minutes** (`BUFFER_DURATION_SECONDS=1200`). Default user delay **14 s** (`LIVE_DELAY_SECONDS=14`).

The camera is programmed via ONVIF so the Pi can **copy bitstreams** (`-c:v copy`) — no Pi transcode in the default product path.

---

## 2. Storage

| Store          | Medium           | Size (steady state)                               |
| -------------- | ---------------- | ------------------------------------------------- |
| HLS 4K + 1080p | **microSD disk** | ~2.7 GB combined (see `spec-video-resolution.md`) |

HLS is disk-backed — **not RAM**.

Segment writers create ~1 s fMP4 files and delete segments older than the 20‑minute window (`hls_flags delete_segments+append_list`). That continuous write/delete cycle is what lets coaches and sports participants scrub the rolling buffer while delayed HDMI/Wi‑Fi playback continues. It also wears the microSD; treat card replacement (or USB SSD for buffers) as expected maintenance for unattended, long‑running units — see `spec-video-resolution.md` §2.

---

## 3. Requirements

| #   | Requirement                                                                                         |
| --- | --------------------------------------------------------------------------------------------------- |
| 1   | Camera main stream configured via ONVIF — **≥ 25 fps**, GOP **25 frames** (1 keyframe/s at 25 fps). |
| 2   | When main > 1080p: camera **sub stream** at 1080p H.264 @ 25 fps for Wi‑Fi.                         |
| 3   | **All branches**: remux/copy — **no Pi scale/encode** in production.                                |
| 4   | Rolling **20 min** on both HLS tiers; delete older segments.                                        |
| 5   | Serve **1080p** playlist/segments over HTTP to Wi‑Fi clients only.                                  |
| 6   | **Main-resolution** HLS on disk — **not** exposed on Wi‑Fi AP.                                      |
| 7   | HLS segment duration **1 s** aligned with camera GOP.                                               |
| 8   | Continue writing while clients read; support multiple Wi‑Fi readers.                                |
| 9   | HDMI delayed playback reads **4K HLS** (`hls-4k/`) — see `spec-hdmi-output.md`.                     |
| 10  | Show Live plays **RTSP main** directly — replay buffer stopped.                                     |

---

## 4. Segment Design (HLS tiers)

| Parameter        | Value                                                      |
| ---------------- | ---------------------------------------------------------- |
| Format           | HLS + **fMP4** (CMAF-style)                                |
| Segment duration | **1 s**                                                    |
| Codec            | Match camera (H.264 main/sub; H.265 on main if configured) |
| Audio            | **None**                                                   |
| IDR / keyframe   | **≤ 1 segment** — camera GOP 25 @ 25 fps                   |

Frequent keyframes (1 per second) are required for smooth Android timeline scrubbing.

---

## 5. ffmpeg Dual Output, Remux Only

When main is 4K/1440p and sub is 1080p — implemented in `ldrs-replay-buffer.sh`:

```bash
ffmpeg -rtsp_transport tcp -i "$RTSP_MAIN" \
       -rtsp_transport tcp -i "$RTSP_SUB" \
  -an \
  -map 0:v:0 -c:v copy -f hls -hls_segment_type fmp4 \
    -hls_time 1 -hls_list_size 1200 -hls_flags delete_segments+append_list \
    /var/lib/sportassist/hls-4k/live.m3u8 \
  -map 1:v:0 -c:v copy -f hls -hls_segment_type fmp4 \
    -hls_time 1 -hls_list_size 1200 -hls_flags delete_segments+append_list \
    /var/lib/sportassist/hls/live.m3u8
```

When only one stream is configured (main ≤1080p), both HLS outputs map from the same RTSP input.

Pi transcode is **not** the default — see `spec-camera-stream-profiles.md` §1 for exceptions.

---

## 6. Delay model

Consumer mapping (formula, tuning, `PLAYBACK_OFFSET`): **`.cursor/spec-hdmi-output.md` §3**.

| Consumer  | Mechanism                                           |
| --------- | --------------------------------------------------- |
| **HDMI**  | `delayed_hdmi.m3u8` + **cvlc** (or RTSP + **cvlc**) |
| **Wi‑Fi** | `delayed_sync.m3u8` with `#EXT-X-START`             |

Wi‑Fi playlist: `lib.wifi_scrub_playlist` (`ldrs-hls-delay-playlists.service`); Flask may rebuild via `ensure_wifi_delayed_playlist()` in `app.py`.

---

## 7. Services

| Unit                               | Role                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------- |
| `ldrs-replay-buffer.service`       | `ExecStartPre`: clear HLS; `ExecStart`: ffmpeg dual HLS                    |
| `ldrs-hls-delay-playlists.service` | `delayed_sync.m3u8` + `delayed_hdmi.m3u8` updater; `BindsTo` replay buffer |
| `ldrs-hdmi-delay.service`          | **cvlc** on 4K `delayed_hdmi.m3u8` or RTSP main (delayed)                  |
| `ldrs-hdmi-live.service`           | **cvlc** / **mpv** on RTSP main (Show Live)                                |

Switching from **Show Live** to **Delayed** clears HLS buffers via `ldrs-hdmi-activate.sh` before starting replay buffer.

---

## 8. Configuration

Timing keys: `.cursor/architecture-and-technical-spec.md` §7.1. Ingest dimensions: `camera.env` (`INGEST_*`, `INGEST_SUB_*`) after ONVIF configure.

---

## 9. HTTP URLs

Wi‑Fi HLS and status URLs: `.cursor/spec-api-endpoints.md` §2–§3.

---

## 10. Acceptance criteria

1. Both HLS buffers span ~20 min after soak; total disk ~2.7 GB ± 15% (4K main + 1080p sub).
2. Wi‑Fi serves **1080p** only; main-res buffer not reachable from AP clients.
3. HDMI delayed plays **main stream** via 4K HLS at **`LIVE_DELAY_SECONDS`** (tuned).
4. Three tablets scrub 1080p HLS concurrently without separate Pi copies.
5. Production path uses **remux only** — no Pi ffmpeg encode on any branch.
6. Changing `LIVE_DELAY_SECONDS` does not require replay-buffer restart.
