# Live Video Delay Replay System – Architecture and Technical Specification

Single reference for appliance architecture and low-level behaviour.  
For AI assistant meta-rules, see `.cursor/constitution.md`.

---

## 1. Product Overview

**Goal**: Build an **open-source sports replay appliance** on Raspberry Pi 5 that:

- Connects to **one PoE IP camera** over Ethernet via **authenticated RTSP**.
- **Owns** camera credentials, ingest, delay, and replay buffering on the Pi.
- Maintains a **rolling 20-minute HLS/fMP4 replay buffer** on the Pi (not on clients).
- Serves the **1080p Wi‑Fi HLS buffer** to **Android / iOS** apps and drives **4K HDMI** for the coach monitor.
- Provides a **password-protected Settings** web UI (usable from a mobile browser or in-app WebView).
- Controls lens via **ONVIF**; persists delay, HDMI mode, presets, and network mode.

**Primary clients**: Native **Android (Kotlin)** and, eventually, **iOS (Swift)** apps — delayed HLS replay + Settings. See `.cursor/spec-mobile-clients.md`.

**Coach live / near-live video**: **HDMI 4K only** (delayed or live toggle on Settings) — **not** WebRTC or a browser player.

**Explicitly not in v2**: WebRTC, unauthenticated Wi‑Fi replay, live-focus web page — see `.cursor/constitution.md` §3.1. Browser replay at `/replay` exists but requires the same web login as HLS.

**Mobile apps are developed in separate repositories/projects**, not inside this repo. This repository owns the Pi appliance and HTTP contract only.

**Mobile apps must not** create the replay buffer locally, connect to the camera RTSP, or hold camera credentials.

### Target platform

- Raspberry Pi 5 Model B — **4 GB RAM minimum** (current manufacturing build); **8 GB recommended** for headroom under full 4K dual-buffer + multiple Wi‑Fi clients.
- **64 GB microSD minimum** (128 GB recommended) — see `.cursor/spec-video-resolution.md` for storage budget.
- Raspberry Pi OS Lite – 64‑bit.
- **4K HDMI** monitor for poolside coach display.
- Headless operation; no desktop required for normal running.

### Camera

- Preferred model: `.cursor/NetworkCameraSpec.md`.
- PoE via injector or switch.

---

## 2. Agreed Architecture

```text
IP camera
    │  RTSP (Ethernet, authenticated)
    ▼
Raspberry Pi 5 replay appliance
    │  ingest → remux → rolling 20 min HLS/fMP4 buffer (no Pi transcode)
    │  HTTP: playlist + segments + optional status API
    ▼
Android Kotlin app (Wi‑Fi AP) — see AndroidAppMobile/ (separate development)
    │  ExoPlayer / Media3 — delayed playback + timeline scrub
    ▼
Athlete / coach review (no local buffer on device)

[iOS Swift app — planned, separate development]
    │  AVPlayer — same HTTP contract as Android
    ▼
Athlete / coach review (no local buffer on device)
```

**Commercial reasoning**: The Pi is the product — it owns camera access, buffering, delay, and serving. Mobile apps (Kotlin / Swift) stay simple, secure, and maintainable. Multiple clients read the **same** Pi buffer without each creating a copy.

---

## 3. High-Level Component Diagram

```text
PoE IP Camera (RTSP + ONVIF)
    ▼
Raspberry Pi 5
    ├── ldrs-wifi-ap          wlan0 AP — sport-assist-{serial}
    ├── ldrs-network          eth0 — optional camera DHCP
    ├── ldrs-camera-discovery
    ├── ldrs-replay-buffer    RTSP → dual fMP4 HLS (4K main + 1080p sub)
    ├── ldrs-hls-delay-playlists  Wi‑Fi delayed_sync.m3u8 (#EXT-X-START)
    ├── ldrs-web              Flask — /hls/*, /api/status, /settings
    ├── ldrs-hdmi-delay       4K HDMI — cvlc on delayed HLS or RTSP (spec-hdmi-output.md)
    ├── ldrs-hdmi-live        Show Live — cvlc RTSP direct
    └── onvif-lens            settings-driven lens control
         │
         ├── HTTP :8080 → Android / iOS apps (`/hls/*`, `/api/status`, `/settings`)
         └── HDMI 4K → coach monitor (delayed or live)
```

**Not in v2:** WebRTC; unauthenticated Wi‑Fi replay; live-focus web page. Browser `/replay` requires web login (`constitution.md` §3.1).

---

## 4. Raspberry Pi 5 Responsibilities

| Responsibility                                                           | Owner                                            |
| ------------------------------------------------------------------------ | ------------------------------------------------ |
| RTSP connect to camera                                                   | `ldrs-replay-buffer` (+ discovery)               |
| Transcode or remux to HLS/fMP4 (CMAF-style where possible)               | `ldrs-replay-buffer`                             |
| Rolling **20 minute** segment store                                      | `ldrs-replay-buffer`                             |
| Delete segments older than 20 minutes                                    | `ldrs-replay-buffer`                             |
| Serve playlist + segments over HTTP                                      | `ldrs-web` (Flask)                               |
| Default **~14 s** behind live at playback edge                           | HDMI: wall-clock ring; Wi‑Fi: HLS `#EXT-X-START` |
| Continue writing while clients read older segments                       | required                                         |
| Wi‑Fi AP for Android                                                     | `ldrs-wifi-ap`                                   |
| Configure camera (ONVIF interrogate + **auto-configure stream profile**) | Settings → `/api/camera/*` → `camera.env`        |
| HDMI delayed output                                                      | `ldrs-hdmi-delay` (cvlc on delayed HLS or RTSP)  |
| Settings / ONVIF                                                         | `ldrs-web`                                       |

Detail: `.cursor/spec-hls-replay-buffer.md`, `.cursor/spec-rtsp-ingest.md`, `.cursor/spec-api-endpoints.md`.

---

## 5. Mobile clients

Native Android (Kotlin) and iOS (Swift, planned) — developed outside this repo. Rules, login flow, and acceptance tests: **`.cursor/spec-mobile-clients.md`**. Platform UI: `spec-android-app.md`, `spec-ios-app.md`.

---

## 6. Network Model

```text
[Camera] ── Ethernet ── [Pi eth0]
[Android / iOS] ── Wi‑Fi AP ── [Pi wlan0] ── HTTP only ──► Pi replay endpoints
```

- Pi is the **controlled gateway** between camera and apps.
- Mobile clients talk **only** to Pi HTTP endpoints on the AP (default base `http://192.168.4.1`).
- Camera stays on Ethernet; never on app Wi‑Fi path.
- **Multiple clients** (Android and/or iOS) may read the same HLS/fMP4 buffer concurrently.

Detail: `.cursor/spec-wifi-ap.md`, `.cursor/spec-network-dhcp.md`.

---

## 7. Configuration (`/etc/sportassist/`)

### 7.1 `system.env`

| Key                          | Default   | Purpose                                                     |
| ---------------------------- | --------- | ----------------------------------------------------------- |
| `LIVE_DELAY_SECONDS`         | `14`      | User delay; **HDMI wall-clock ring**; Wi‑Fi target          |
| `PIPELINE_LATENCY_SECONDS`   | `3`       | Camera→HLS-edge latency; Wi‑Fi `PLAYBACK_OFFSET` only       |
| `BUFFER_DURATION_SECONDS`    | `1200`    | Rolling HLS window (20 min)                                 |
| `HLS_SEGMENT_DURATION`       | `1`       | Target HLS segment length (seconds)                         |
| `HDMI_ENABLED`               | `1`       | HDMI output service                                         |
| `HDMI_OUTPUT_MODE`           | `delayed` | `delayed` or `live` (Show Live) — see `spec-hdmi-output.md` |
| `HDMI_PLAYBACK_BIAS_SECONDS` | `0`       | Optional HDMI fine-tune (positive = less delay)             |
| `HDMI_VLC_CACHING_MS`        | `200`     | cvlc fallback buffer (delayed HDMI)                         |
| `HDMI_LIVE_CACHING_MS`       | `100`     | VLC buffer when `HDMI_OUTPUT_MODE=live`                     |

### 7.2 Other files

- `camera.env` — RTSP/ONVIF credentials (Pi only).
- `network.env` — `ETH_CAMERA_DHCP`, eth0 camera link.
- `wifi-ap.env` — AP SSID/password.
- `web.env` — web login and Flask session — see `spec-settings-page.md` §3.
- `lens-presets.json` — ONVIF lens presets.

Segment files on disk (runtime): e.g. `/var/lib/sportassist/hls/` (exact path in `spec-hls-replay-buffer.md`).

---

## 8. Playback behaviour

Delay semantics: `.cursor/spec-hdmi-output.md` §3. Mobile client rules: `.cursor/spec-mobile-clients.md` §2.

---

## 9. Systemd Boot Order

```text
ldrs-wifi-ap.service
        ↓
ldrs-network.service
        ↓
ldrs-camera-discovery.service
        ↓
ldrs-replay-buffer.service      # RTSP ingest → dual HLS writers
        ↓
ldrs-hls-delay-playlists.service   # Wi‑Fi delayed_sync.m3u8 (BindsTo replay buffer)
        ↓
ldrs-hdmi-delay.service         (After replay buffer; cvlc on delayed HLS or RTSP)
ldrs-web.service                (After network.target)
```

---

## 10. Testing Methodology (Layered)

1. Ethernet / DHCP / camera discovery
2. RTSP auth (`ffprobe`)
3. Segment writer — files appear, timestamps advance
4. Rolling deletion — nothing older than 20 min
5. `GET /hls/live.m3u8` + segment GET from AP client
6. Android — default ~14 s delay, scrub across buffer
7. Multi-client — two devices read same buffer
8. ONVIF / settings / optional HDMI
9. 30-minute soak

Never start debugging at the Android UI layer.

---

## 11. Acceptance criteria

**Pi buffer and ingest:** `.cursor/spec-hls-replay-buffer.md` (acceptance section).  
**Mobile clients:** `.cursor/spec-mobile-clients.md` §4.  
**System integration:** Wi‑Fi AP always on; camera on Ethernet only; HDMI and settings functional.

---

## 12. Related Specifications

| Topic                   | Document                                 |
| ----------------------- | ---------------------------------------- |
| Rolling HLS/fMP4 buffer | `.cursor/spec-hls-replay-buffer.md`      |
| HTTP endpoints          | `.cursor/spec-api-endpoints.md`          |
| Android app             | `.cursor/spec-android-app.md`            |
| RTSP ingest             | `.cursor/spec-rtsp-ingest.md`            |
| RTSP stream profiles    | `.cursor/spec-camera-stream-profiles.md` |
| Wi‑Fi AP                | `.cursor/spec-wifi-ap.md`                |
| Ethernet / DHCP         | `.cursor/spec-network-dhcp.md`           |
| Settings UI             | `.cursor/spec-settings-page.md`          |
| HDMI                    | `.cursor/spec-hdmi-output.md`            |
