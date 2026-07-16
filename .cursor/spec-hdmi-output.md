# Spec: HDMI 4K Output

Normative specification for **3840×2160** poolside HDMI coaching display — **as implemented and deployed on the Pi**.

Related: `.cursor/spec-video-resolution.md`, `.cursor/spec-settings-page.md` §5, `.cursor/NetworkCameraSpec.md`, `.cursor/spec-hls-replay-buffer.md`.

---

## 1. Purpose

Fullscreen **4K UHD** on a wired HDMI monitor — independent of Wi‑Fi tablet traffic.

| Mode                    | Settings label                  | Service                   | Purpose                                           |
| ----------------------- | ------------------------------- | ------------------------- | ------------------------------------------------- |
| **`delayed`** (default) | **Delayed** (Show Live **off**) | `ldrs-hdmi-delay.service` | Coach replay **`LIVE_DELAY_SECONDS`** behind live |
| **`live`**              | **Show Live**                   | `ldrs-hdmi-live.service`  | Direct **RTSP** to HDMI — replay buffer stopped   |

**Show Live** stops `ldrs-replay-buffer`, `ldrs-hdmi-delay`, and Wi‑Fi delayed playlists.

**Delayed** keeps `ldrs-replay-buffer` running. ffmpeg writes dual fMP4 HLS buffers (4K main + 1080p sub). HDMI plays delayed output via **cvlc** on `delayed_hdmi.m3u8` (dual-stream ingest) or RTSP+cvlc.

---

## 2. Delayed HDMI pipeline (production)

```text
Camera RTSP (main + sub)
    ▼
ffmpeg (ldrs-replay-buffer) — remux copy, dual HLS only
    ├── fMP4 HLS → /var/lib/sportassist/hls-4k/live.m3u8   (buffer / status; not played on HDMI)
    └── fMP4 HLS → /var/lib/sportassist/hls/live.m3u8      (1080p sub — Wi‑Fi)

ldrs-hdmi-delay.service
    └── cvlc on RTSP main (second connection) — live-caching = LIVE_DELAY_SECONDS

ldrs-hls-delay-playlists.service
    ├── hls/delayed_sync.m3u8          (1080p full buffer + #EXT-X-START — tablets)
    └── hls-4k/delayed_hdmi.m3u8       (status / diagnostic)

ldrs-hdmi-live.service (Show Live)
    └── cvlc on RTSP main — minimal cache (live-caching=0)
```

| Component                         | Path / unit                                                                   |
| --------------------------------- | ----------------------------------------------------------------------------- |
| HDMI primary source (dual-stream) | `/var/lib/sportassist/hls-4k/delayed_hdmi.m3u8`                               |
| HDMI player                       | `ldrs-hdmi-delay.service` → **cvlc** (HLS or RTSP); **mpv** fallback for RTSP |
| Delayed playlist builder          | `ldrs-hls-delay-playlists.service`                                            |
| Idle logo                         | `ldrs-hdmi-idle.service`                                                      |
| Ingest                            | `ldrs-replay-buffer.service`                                                  |

Delayed HDMI uses the **4K HLS disk buffer** (main stream remux). Show Live bypasses ingest and plays **RTSP main** directly.

---

## 3. Delay semantics

`LIVE_DELAY_SECONDS` is the **user-facing wall-clock target** (default 14 s): how far behind pool-side live the coach monitor should be.

The HLS live edge lags true live by ingest latency **`PIPELINE_LATENCY_SECONDS`**. HDMI and Wi‑Fi therefore use the same edge offset:

```text
PLAYBACK_OFFSET = LIVE_DELAY_SECONDS − PIPELINE_LATENCY_SECONDS − HDMI_PLAYBACK_BIAS_SECONDS
```

Approximate wall-clock delay at playback:

```text
wall_clock_delay ≈ PIPELINE_LATENCY_SECONDS + PLAYBACK_OFFSET
                 = LIVE_DELAY_SECONDS − HDMI_PLAYBACK_BIAS_SECONDS
```

| Example (`LIVE_DELAY=14`, `PIPELINE_LATENCY=3`, bias `0`) | Value                    |
| --------------------------------------------------------- | ------------------------ |
| `PLAYBACK_OFFSET` (seek / `#EXT-X-START`)                 | **11 s** behind HLS edge |
| Target wall-clock delay                                   | **14 s**                 |

**Tuning:** If HDMI measures short or long vs pool live, adjust **`PIPELINE_LATENCY_SECONDS`** in `/etc/sportassist/system.env` to match real ingest lag (often **~3 s** on Pi, not 7). Then restart `ldrs-hls-delay-playlists` and `ldrs-hdmi-delay`.

Fine-tune per install with **`HDMI_PLAYBACK_BIAS_SECONDS`** (positive = less delay).

Delayed HDMI uses a **second RTSP read** of the camera main stream (ffmpeg keeps the first for HLS). VLC `live-caching` provides wall-clock delay without HLS fmp4 timing issues.

### HDMI playback commands (as deployed)

```bash
# Delayed — primary (ldrs-hdmi-delay.sh) — RTSP main + VLC cache
cvlc "rtsp://…" --rtsp-tcp --rtsp-frame-buffer-size=10000000 \
  --live-caching=$((LIVE_DELAY_SECONDS * 1000)) \
  --network-caching=$((LIVE_DELAY_SECONDS * 1000)) \
  --file-caching=0 --clock-jitter=0 --clock-synchro=0 \
  --no-audio --fullscreen --quiet

# Show Live (ldrs-hdmi-live.sh)
cvlc "rtsp://…" --rtsp-tcp --rtsp-frame-buffer-size=10000000 \
  --live-caching=0 --network-caching=0 --file-caching=0 \
  --clock-jitter=0 --clock-synchro=0 \
  --no-audio --fullscreen --quiet

# Show Live — mpv fallback
mpv --no-config --hwdec=v4l2m2m --rtsp-transport=tcp --cache=yes \
  --no-audio --fullscreen --force-window=immediate \
  "rtsp://…"
```

Install **cvlc** (VLC) on the Pi for both HDMI modes. **mpv** is fallback for RTSP and used for the idle logo.

---

## 4. Sources and modes

| Mode               | Source                                  | Player                    | Ingest                       |
| ------------------ | --------------------------------------- | ------------------------- | ---------------------------- |
| Delayed            | `rtsp://…` main stream (2nd connection) | **cvlc** (`live-caching`) | `ldrs-replay-buffer` **on**  |
| Delayed (fallback) | `rtsp://…` main                         | **mpv**                   | `ldrs-replay-buffer` **on**  |
| Show Live          | `rtsp://…` main                         | **cvlc**, then **mpv**    | `ldrs-replay-buffer` **off** |

| Parameter     | Delayed                                                             | Show Live           |
| ------------- | ------------------------------------------------------------------- | ------------------- |
| Resolution    | Up to **3840×2160**                                                 | Up to **3840×2160** |
| Latency       | **`LIVE_DELAY_SECONDS`** wall-clock (when `PIPELINE_LATENCY` tuned) | Minimum — RTSP only |
| Replay buffer | Running                                                             | **Stopped**         |
| Wi‑Fi HLS     | Updating                                                            | **Paused**          |

---

## 4.1 Idle logo (no video)

When HDMI is enabled but no video player owns the display:

| Asset | `/usr/share/sportassist/SportAssistLogo.png` (50% screen via mpv `--autofit=50%`) |
| Title | `/usr/share/sportassist/SportAssistIdle.ass` — “Sport Assist” below logo (mpv subtitles) |
| Service | `ldrs-hdmi-idle.service` |
| Scripts | `ldrs-hdmi-idle-start.sh`, `ldrs-hdmi-idle-stop.sh` (sudo via `systemctl`) |

Logo appears during:

- Boot / buffer warm-up (~`LIVE_DELAY_SECONDS` after mode change)
- Player exit and reconnect retries
- Pipelines stopped while HDMI remains enabled

**Show Live:** `ldrs-hdmi-idle-start.sh` **does not** start the logo when `HDMI_OUTPUT_MODE=live`.

`ldrs-hdmi-delay.sh` and `ldrs-hdmi-live.sh` call `ldrs-hdmi-idle-stop.sh` before playback. `ExecStopPost` on both HDMI player units can restore the logo when the service stops (unless mode is live).

---

## 5. Mode switching

Settings **Show Live** toggle → `POST /settings/hdmi/mode` → `ldrs-set-hdmi-mode.sh`:

1. Write `HDMI_OUTPUT_MODE` to `system.env` **first** (so stop hooks see target mode)
2. Run `ldrs-hdmi-activate.sh`
3. On failure, **restore** previous `system.env`

`ldrs-hdmi-activate.sh` calls `ldrs-stop-video-pipelines.sh`, which **force-stops** units (up to 15 s, then SIGKILL) so mode changes do not hang on a stuck mpv/ffmpeg.

| Transition    | Effect                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------ |
| → **live**    | Stop replay buffer, hdmi-delay, playlists; start `ldrs-hdmi-live`                          |
| → **delayed** | Clear HLS buffers; start replay buffer, playlists, `ldrs-hdmi-delay`; show idle until warm |

Settings HDMI mode API timeout: **120 s** (client matches).

---

## 6. Configuration (`system.env`)

```bash
HDMI_ENABLED=1
HDMI_OUTPUT_MODE=delayed    # delayed | live
LIVE_DELAY_SECONDS=14
PIPELINE_LATENCY_SECONDS=3  # tune to real ingest lag — used for HDMI + Wi‑Fi offset
HDMI_PLAYBACK_BIAS_SECONDS=0
HDMI_VLC_CACHING_MS=200
HDMI_LIVE_CACHING_MS=100
```

| Key                          | Default (template) | Purpose                                                     |
| ---------------------------- | ------------------ | ----------------------------------------------------------- |
| `HDMI_ENABLED`               | `1`                | `0` stops HDMI services; replay buffer stays on for tablets |
| `HDMI_OUTPUT_MODE`           | `delayed`          | `live` = Show Live                                          |
| `LIVE_DELAY_SECONDS`         | `14`               | Wall-clock delay target (HDMI + user-facing)                |
| `PIPELINE_LATENCY_SECONDS`   | `3`                | Camera → HLS-edge latency; drives `PLAYBACK_OFFSET`         |
| `HDMI_PLAYBACK_BIAS_SECONDS` | `0`                | Fine-tune (positive = less delay)                           |
| `HDMI_VLC_CACHING_MS`        | `200`              | cvlc delayed-HLS fallback only                              |

**Helpers**:

| Script                                | Purpose                                            |
| ------------------------------------- | -------------------------------------------------- |
| `ldrs-set-hdmi-mode.sh delayed\|live` | Update mode + activate (rollback on failure)       |
| `ldrs-set-hdmi-enabled.sh 0\|1`       | HDMI on/off                                        |
| `ldrs-hdmi-activate.sh`               | Stop/start replay buffer + correct HDMI unit       |
| `ldrs-stop-video-pipelines.sh`        | Force-stop all video units                         |
| `ldrs-diagnose-hdmi-delay.sh`         | Playlists, ring status, services                   |
| `ldrs-delay-env.sh`                   | Shared `PLAYBACK_OFFSET` math (sourced by scripts) |

`ldrs-hdmi-apply.service` runs on boot to apply `HDMI_OUTPUT_MODE`.

---

## 7. Settings UI

- **HDMI on/off** — `POST /settings/hdmi/enabled`
- **Show Live** toggle — `POST /settings/hdmi/mode` (`live` = Show Live on)
- ONVIF lens controls remain available in Show Live mode

---

## 8. systemd units

| Unit                               | Role                                                              |
| ---------------------------------- | ----------------------------------------------------------------- |
| `ldrs-hdmi-apply.service`          | Boot: apply `HDMI_OUTPUT_MODE`                                    |
| `ldrs-hdmi-idle.service`           | Fullscreen logo when no video                                     |
| `ldrs-hdmi-delay.service`          | Delayed 4K HLS playback (**cvlc** on `delayed_hdmi.m3u8` or RTSP) |
| `ldrs-hdmi-live.service`           | Show Live RTSP (cvlc / mpv)                                       |
| `ldrs-replay-buffer.service`       | ffmpeg dual HLS (4K main + 1080p sub)                             |
| `ldrs-hls-delay-playlists.service` | `delayed_sync.m3u8` + `delayed_hdmi.m3u8`                         |

HDMI player units use `TimeoutStopSec=10` and `KillMode=control-group` so stops complete reliably.

---

## 9. API (`GET /api/status`)

```json
{
  "hdmiEnabled": true,
  "hdmiOutputMode": "delayed",
  "hdmiFocusMode": false,
  "liveDelaySeconds": 14,
  "hdmiDelaySeconds": 14,
  "playbackOffsetSeconds": 11,
  "pipelineLatencySeconds": 3,
  "delayedHdmiReady": true,
  "delayedSyncReady": true
}
```

| Field                                   | Purpose                                                               |
| --------------------------------------- | --------------------------------------------------------------------- |
| `liveDelaySeconds` / `hdmiDelaySeconds` | Wall-clock delay target (`LIVE_DELAY − bias`)                         |
| `playbackOffsetSeconds`                 | Seconds behind HLS live edge (`PLAYBACK_OFFSET`) — **HDMI and Wi‑Fi** |
| `pipelineLatencySeconds`                | Configured ingest lag                                                 |
| `delayedHdmiReady`                      | Enough 4K HLS segments for configured delay                           |
| `delayedSyncReady`                      | Wi‑Fi `delayed_sync.m3u8` fresh                                       |

`bufferHealth` is `"focus"` when Show Live is active.

---

## 10. Acceptance criteria (field-tested)

1. **Delayed**: HDMI within ~1–2 s of **`LIVE_DELAY_SECONDS`** when `PIPELINE_LATENCY_SECONDS` is tuned; replay buffer writing; tablets updating.
2. **Show Live**: HDMI shows direct RTSP via cvlc; `ldrs-replay-buffer` inactive; no new `.m4s` files.
3. Toggling delayed ↔ Show Live completes within **~15 s** (force-stop prevents hung switches).
4. No WebRTC endpoints in v2.
5. Returning to delayed clears HLS, restarts ingest, resumes HDMI + tablets within **`LIVE_DELAY_SECONDS` + ~5 s** warm-up.
6. Delay change via Settings updates `system.env`, restarts `ldrs-hls-delay-playlists` and **`ldrs-hdmi-delay`** (mpv reopens trimmed playlist). mpv also restarts if `PLAYBACK_OFFSET` changes while running.
7. When no video is playing (warm-up, reconnect, player stopped), HDMI shows `SportAssistLogo.png` (not during Show Live idle suppression).

---

## 11. Operational notes

| Symptom                 | Check                                                                                     |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| HDMI black, logo gone   | `systemctl status ldrs-hdmi-delay`; `pgrep -a mpv`; `/var/log/sportassist/hdmi-delay.log` |
| HDMI short/long vs live | Tune `PIPELINE_LATENCY_SECONDS`; verify `playbackOffsetSeconds` in `/api/status`          |
| Show Live no picture    | `systemctl status ldrs-hdmi-live`; `/var/log/sportassist/hdmi-live.log`                   |
| Mode switch stuck       | `ldrs-stop-video-pipelines.sh`; `systemctl reset-failed ldrs-hdmi-*`                      |
| Ring status only        | `ldrs-diagnose-hdmi-delay.sh` — HLS playlists, services, mpv                              |

**Deploy:** Pi code under `pi-root/`; after extract, `sudo systemctl daemon-reload` and restart affected units.
