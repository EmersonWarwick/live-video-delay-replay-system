# Spec: Video Resolution and Storage Tiers

Normative specification for **capture, buffer, HDMI, and Wi‑Fi** resolutions on Raspberry Pi 5.

Related: `.cursor/NetworkCameraSpec.md`, `.cursor/spec-hls-replay-buffer.md`, `.cursor/spec-hdmi-output.md`, `.cursor/spec-android-app.md`, `.cursor/spec-camera-stream-profiles.md`.

---

## 1. Design Decision — Tiered Resolution

One **camera RTSP ingest** on Ethernet — **resolution and codec programmed by Pi via ONVIF** using the fallback ladder; **two remux-only outputs** on the Pi:

| Tier                              | Resolution                                              | Frame rate   | Primary use             | Delivery                                                |
| --------------------------------- | ------------------------------------------------------- | ------------ | ----------------------- | ------------------------------------------------------- |
| **Main ingest (ONVIF)**           | **3840×2160**, **2560×1440**, or **1920×1080** (ladder) | **≥ 25 fps** | HDMI buffer source      | Camera main RTSP — see `spec-camera-stream-profiles.md` |
| **Sub ingest (when main >1080p)** | **1920×1080** H.264                                     | 25 fps       | Wi‑Fi buffer source     | Camera sub RTSP — remux only                            |
| **A — HDMI / coach display**      | Matches main ingest                                     | ≥ 25 fps     | Delayed fullscreen HDMI | Local `hls-4k/` playback                                |
| **B — Wi‑Fi clients**             | **1920 × 1080** fixed                                   | 25 fps       | Android scrub           | `GET /hls/live.m3u8`                                    |

**Why not 4K over Wi‑Fi to a 10″ tablet?**

- Viewing distance on pool deck does not benefit from 4K on ~10″ display.
- Pi AP (typically 2.4 GHz) shared bandwidth ~20–40 Mbps practical; 4K HLS (~12–20 Mbps **per client**) does not scale to multiple tablets scrubbing.
- **1080p @ 4–6 Mbps** per client is the best balance of clarity, scrub responsiveness, and multi-client stability.

**Why 4K on HDMI?**

- Poolside coach monitor is larger; 4K preserves dive detail for coaching review.
- HDMI is wired; no Wi‑Fi contention.

---

## 2. Hardware Requirements (4K Product Tier)

| Component           | Specification                                         | Rationale                                                             |
| ------------------- | ----------------------------------------------------- | --------------------------------------------------------------------- |
| **Raspberry Pi 5**  | **4 GB RAM minimum** (manufacturing build)            | Dual RTSP remux + HDMI + Wi‑Fi concurrently                           |
|                     | **8 GB RAM**                                          | Recommended for headroom under full 4K dual-buffer + multiple tablets |
| **Storage**         | **64 GB** microSD minimum (128 GB recommended)        | 4K + 1080p rolling buffers + OS headroom                              |
| **HDMI**            | 4K-capable monitor + appropriate Pi firmware settings | See `spec-hdmi-output.md`                                             |
| **Camera Ethernet** | Gigabit path preferred                                | 4K H.264 ~12 Mbps sustained                                           |

The **20-minute HLS buffer lives on the SD card** (disk-backed fMP4 segments) plus ffmpeg/mpv working buffers in RAM.

**Flash wear:** Delayed mode writes and deletes ~1‑second segments continuously so coaches and participants can review the rolling loop before and during delayed live feedback. Expect the microSD to wear out eventually under that duty cycle; use a high‑endurance card, keep a spare, and optionally move buffers to USB SSD for high‑duty installations.

---

## 3. Storage Budget — 20 Minutes on 64 GB SD

### Tier A — 4K HDMI buffer

| Parameter          | Value                                                         |
| ------------------ | ------------------------------------------------------------- |
| Resolution         | 3840 × 2160                                                   |
| Codec              | H.264 (remux from camera when possible)                       |
| Target bitrate     | **12 Mbps**                                                   |
| Duration           | 20 min (1200 s)                                               |
| **Estimated size** | 12 × 1200 ÷ 8 ≈ **1.8 GB** (+ ~5% fMP4 overhead ≈ **1.9 GB**) |

### Tier B — 1080p Wi‑Fi HLS buffer

| Parameter          | Value                                                |
| ------------------ | ---------------------------------------------------- |
| Resolution         | 1920 × 1080                                          |
| Codec              | H.264                                                |
| Target bitrate     | **5 Mbps**                                           |
| Duration           | 20 min                                               |
| **Estimated size** | 5 × 1200 ÷ 8 ≈ **0.75 GB** (+ overhead ≈ **0.8 GB**) |

### Combined

| Item                            | Size        |
| ------------------------------- | ----------- |
| 4K buffer                       | ~1.9 GB     |
| 1080p buffer                    | ~0.8 GB     |
| **Total rolling media**         | **~2.7 GB** |
| OS + apps (reserved)            | ~10 GB      |
| **Free headroom on 64 GB card** | **~51 GB**  |

**Verdict**: **64 GB SD is sufficient** for 20 minutes of **4K + 1080p** rolling buffers alongside the OS. Use **`/var/lib/sportassist/`** on the SD root partition; do not use tmpfs for the 20-minute store.

Optional: dedicate an ext4 partition or **USB SSD** for `/var/lib/sportassist/hls*` in high-duty installations to reduce microSD wear — not required for the default v2 build.

---

## 4. Ingest Pipeline (Remux-Only)

```text
Pi ONVIF: configure camera main (+ sub @ 1080p when main > 1080p)
    │  GOP 25 frames, 25 fps, H.265→H.264 fallback on main
    ▼
Camera RTSP main ──► ffmpeg -c:v copy ──► hls-4k/   (HDMI)
Camera RTSP sub  ──► ffmpeg -c:v copy ──► hls/      (Wi‑Fi, 1080p)
```

- **No Pi transcode** in production — camera must output final codec/resolution/fps.
- **INGEST\_\*** and **INGEST*SUB*\*** in `camera.env` reflect ONVIF-applied settings.
- **GOP 25** at 25 fps → 1 keyframe/s → aligns with **1 s** HLS segments for scrubbing.

### Fallback ladder (Pi auto-selects)

1. 4K @ 25 fps: Ultra 265 → H.265 → H.264
2. 1440p @ 25 fps: same codec order
3. 1080p @ 25 fps: H.264 preferred
4. 1080p @ 25 or 30 fps (prefer 25)

Commercial default starting point: **2560×1440** or **3840×2160 @ 25 fps**.

---

## 5. Configuration (`/etc/sportassist/system.env`)

```bash
# Timing — shared buffer (ingest dimensions in camera.env from ONVIF configure)
LIVE_DELAY_SECONDS=14
PIPELINE_LATENCY_SECONDS=3
BUFFER_DURATION_SECONDS=1200
HLS_SEGMENT_DURATION=1
HDMI_PLAYBACK_BIAS_SECONDS=0

# Reference bitrates for ONVIF programming (camera.env INGEST_BITRATE / INGEST_SUB_BITRATE)
HDMI_BUFFER_BITRATE=12000000
WIFI_HLS_BITRATE=5000000
INGEST_GOP=25
```

---

## 6. Wi‑Fi Bandwidth Planning (10″ Tablet)

Assumptions: Pi AP, 2.4 GHz, 1–3 Android tablets, poolside ≤ 10 m.

| Stream                       | Per-client bitrate | 3 clients (approx.) | Fit?              |
| ---------------------------- | ------------------ | ------------------- | ----------------- |
| 1080p HLS scrub              | ~5 Mbps            | ~15 Mbps            | **Yes**           |
| 4K HLS scrub                 | ~12 Mbps           | ~36 Mbps            | **Marginal / no** |
| 1080p Wi‑Fi HLS (×2 clients) | ~5 Mbps each       | ~15 Mbps            | **Yes**           |

Serve **1080p only** on `/hls/live.m3u8`. Do not expose 4K playlist to Wi‑Fi clients.

---

## 7. Acceptance Criteria

Integration checklist — detail in linked specs:

| #   | Criterion                                         | Spec                                      |
| --- | ------------------------------------------------- | ----------------------------------------- |
| 1   | ONVIF configure; ≥ 25 fps; GOP 25; codec fallback | `spec-camera-stream-profiles.md`          |
| 2   | Buffers stable 20+ min; disk as budgeted          | §3 above; `spec-hls-replay-buffer.md` §10 |
| 3   | HDMI delayed at main resolution; remux only       | `spec-hdmi-output.md`                     |
| 4   | Android 1080p HLS over Wi‑Fi                      | `spec-mobile-clients.md` §4               |
| 5   | Pi 5 (4 GB min; 8 GB rec) + 64 GB SD              | §2 above                                  |
| 6   | No Pi transcode on default path                   | `spec-hls-replay-buffer.md` §10           |
