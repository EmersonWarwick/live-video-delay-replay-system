# Live Video Delay Replay System – Cursor Constitution

This document governs how AI assistants working in Cursor must design, modify, and reason about the **Live Video Delay Replay System** Raspberry Pi 5 replay appliance and its **native mobile clients** (Android Kotlin, iOS Swift — developed separately).

If there is ever a conflict about architecture, behaviour, or runtime layout, **`.cursor/architecture-and-technical-spec.md` is the source of truth**.

---

## 1. Document map

Each topic has **one canonical spec**; other documents link to it instead of repeating content.

| Document                                     | Canonical for                                                   |
| -------------------------------------------- | --------------------------------------------------------------- |
| `.cursor/spec-settings-page.md`              | Web login, `/settings` UI, camera/lens on settings              |
| `.cursor/spec-api-endpoints.md`              | HTTP/HLS URLs, request/response shapes                          |
| `.cursor/spec-mobile-clients.md`             | Shared mobile rules and cross-platform acceptance               |
| `.cursor/spec-android-app.md`                | Android screens and ExoPlayer behaviour                         |
| `.cursor/spec-ios-app.md`                    | iOS stack (planned)                                             |
| `.cursor/spec-hls-replay-buffer.md`          | Rolling buffer, ffmpeg, buffer acceptance                       |
| `.cursor/spec-hdmi-output.md`                | HDMI delayed/live pipeline, delay semantics (`PLAYBACK_OFFSET`) |
| `.cursor/spec-video-resolution.md`           | RAM, SD storage budget, 1080p vs 4K tiers                       |
| `.cursor/architecture-and-technical-spec.md` | Appliance overview, systemd, `system.env` keys                  |
| `.cursor/NetworkCameraSpec.md`               | Camera hardware requirements                                    |
| `build-instructions.md`                      | Install index; Mac/PC guides for manufacturing steps            |
| `pi-root/README.md`                          | Runtime tree layout                                             |
| `README.md`                                  | Project overview and quick start                                |
| `CONTRIBUTING.md`                            | Contributor workflow                                            |
| `ROADMAP.md`                                 | Planned direction                                               |
| `.cursor/constitution.md` (this file)        | AI assistant behaviour rules                                    |

**Topic specs (detail — do not duplicate elsewhere):** `spec-camera-discovery.md`, `spec-camera-stream-profiles.md`, `spec-network-dhcp.md`, `spec-wifi-ap.md`, `spec-rtsp-ingest.md`, `spec-onvif-lens.md`, `spec-capture-ffmpeg.md`, `spec-frontend.md`.

---

## 2. Scope and Authority

1. **Open-source replay appliance** — the Raspberry Pi 5 owns camera access, credentials, buffering, delay, and HTTP serving for sports coaching and review.
2. **Mobile apps are thin clients** — playback and scrub only; **no local replay buffer**, **no camera RTSP**, **no camera credentials**.
3. **Mobile apps are developed separately** from this repo:
   - **Android**: Kotlin (Media3 / ExoPlayer) — separate project.
   - **iOS**: Swift (AVPlayer) — planned; separate Swift project.
4. Target appliance: **Raspberry Pi 5**; mobile minimums per `spec-android-app.md` / `spec-ios-app.md`.
5. European English spelling; concrete paths and commands.

---

## 3. Core Invariants (Do Not Violate)

1. **Pi owns the 20-minute rolling HLS/fMP4 buffer** — not MediaMTX short HLS, not Android storage.
2. **Default playback ~14 s behind live** — `LIVE_DELAY_SECONDS=14` unless amended in spec.
3. **Camera RTSP terminates on the Pi** — clients use `GET /hls/live.m3u8` only.
4. **Multiple mobile clients** read the same Pi buffer — no per-device recording.
5. **Wi‑Fi AP always on** — Raspberry Pi **built-in** radio (`brcmfmac` / typically `wlan0`); SSID `sport-assist-{serial}` (legacy prefix); construction password in `config/appliance.env`.
6. **Ethernet camera DHCP** toggled via settings (`ETH_CAMERA_DHCP`) — independent of AP.
7. **Configuration single-sourcing** — `/etc/sportassist/*` (including `web.env` settings password); no duplicated secrets in app or units.
8. **Privileged web changes** — helper scripts + sudoers only.
9. **Prefer fMP4/CMAF HLS** — segments ~0.5–1 s; avoid WebRTC-to-file as main buffer.
10. **Video only** — no audio.

---

## 3.1 Explicit non-requirements (v2)

The following are **out of scope** — do not implement on Pi or in product plans:

| Not required                                                | Use instead                                                                                                                      |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Low-latency live / **WebRTC** over Wi‑Fi                    | **HDMI 4K** — delayed or live via Settings (`HDMI_OUTPUT_MODE`); see `spec-hdmi-output.md`                                       |
| **Browser replay player** (hls.js at `/replay`)             | **Secondary** — requires web login; primary athlete replay is native app                                                         |
| **Unauthenticated HLS / status over Wi‑Fi**                 | **Not in v2** — web session required (see `spec-settings-page.md` §3)                                                            |
| **Live focus web page** / `POST /api/mode` / `:8889` WebRTC | **HDMI 4K** for coach video + **Settings on a mobile device** (`/settings` in app WebView or browser) for lens, HDMI mode, delay |

The Pi serves `/hls/*` to **authenticated** mobile and browser clients (Flask session after web login). It must not build WebRTC or unauthenticated public replay endpoints.

---

## 4. Anti-Patterns (Reject in Code Review)

| Anti-pattern                                                | Why                     |
| ----------------------------------------------------------- | ----------------------- |
| Android `MediaRecorder` / local HLS cache for 20 min replay | Wrong owner             |
| Exposing `rtsp://user:pass@camera` to app                   | Security / support      |
| MediaMTX 3-segment HLS as production scrub store            | Insufficient window     |
| WebRTC recording as primary archive                         | Not agreed architecture |
| Direct camera RTSP in Android production build              | Bypasses appliance      |

---

## 5. Behaviour for AI Assistants

1. Read `architecture-and-technical-spec.md` before implementing.
2. Update specs and code together when architecture changes — **spec first** for new behaviour.
3. Test order: network → RTSP → segment writer → HTTP → client scrub → multi-client.
4. When editing mobile app repos, align with `.cursor/spec-mobile-clients.md` and the platform spec. Pi work in this repo does not require mobile code changes in the same commit.

---

## 6. Relationship to Prior Projects

| Prior                    | Reuse                                      | Do not reuse as primary                                  |
| ------------------------ | ------------------------------------------ | -------------------------------------------------------- |
| Sport-focused prototypes | Delay-buffer architecture, ONVIF configure | Proprietary branding as product identity                 |
| `MobileReplaySystem/`    | Wi‑Fi AP, Flask settings patterns          | MediaMTX / WebRTC live focus; short HLS as 20 min buffer |
| Earlier v1.x             | Wall-clock delay concept                   | USB camera; old VLC-on-HLS HDMI pattern                  |

---

## 7. Amendments

Document constraint changes in the spec that owns them. Preserve: Pi-owned buffer, mobile thin clients, open-source + optional commercial support model.
