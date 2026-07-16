# Camera Specification

## Product Context

The Live Video Delay Replay System uses a single venue IP camera connected to a Raspberry Pi 5 over Ethernet.

The Raspberry Pi:

- Ingests **4K** video from the camera.

- Stores a **20-minute rolling buffer** on SD card (4K for HDMI + 1080p for Wi‑Fi clients).

- Outputs **4K delayed replay** on HDMI for coaching.

- Serves **1080p HLS** to **Android / iOS** apps on the Wi‑Fi AP.

Resolution tiers and storage maths: **`.cursor/spec-video-resolution.md`**.

The camera operates indoors in a well-lit sport pool environment.

---

## Raspberry Pi 5 hardware

Pi RAM, SD size, and 20-minute storage budget: **`.cursor/spec-video-resolution.md` §2–§3**. HDMI must be 4K-capable (display + cable). Buffer is **disk-backed** — not held in RAM.

---

## Camera Model

**First field project:** a **UNV (UniView) CCTV turret** camera commissioned through the vendor’s own Web UI, then assigned to the Pi.

Preferred reference model:

**UNV IPC3638SB-ADZKM-DL-I1**

The integration path is **ONVIF + RTSP** (generic). Other manufacturers are welcome if they meet the requirements below and pass stream-configure / assign acceptance. Community-tested models should be listed as they are validated.

The camera shall support:

- 8 MP image sensor (up to **3840 × 2160**)

- Motorised varifocal lens (2.7 mm – 13.5 mm)

- RTSP streaming

- ONVIF compatibility (Device Management user provisioning + Media stream configuration preferred)

- Video encodings: **Ultra 265**, **H.265**, **H.264**, MJPEG (Pi auto-selects best for replay — Ultra 265 preferred on UNV; MJPEG not used)

- Ethernet connectivity

- PoE (IEEE 802.3af)

### Initial setup via the camera Web UI

Before **Assign camera** on the Pi Settings page, open the camera’s **vendor Web UI** (factory IP or temporary DHCP) and configure at least:

| Setting | Why |
| ------- | --- |
| **Frame rate 25 fps** | Matches HLS segment / GOP alignment (1 keyframe per second at 25 fps) |
| Main / sub encodings | 4K (or ladder) main + 1080p sub for dual-tier remux without Pi transcode |
| Time zone / NTP | Keeps delayed playback aligned to wall clock |
| Indoor day mode | Disable IR, white light, and night modes for lit venues |
| ONVIF + RTSP enabled | Required for discovery, assign, stream configure, and lens control |
| Firmware | Apply vendor updates while you still have direct Web UI access |
| Image check | Confirm exposure, sharpness, and framing on the sport surface |

**Super-user credentials stay private.** Change the factory admin password to a site-owned secret; never commit it, paste it into public issues, or publish it in documentation. Enter that admin login only once when assigning the camera.

---

## System Architecture

The system consists of:

- One **Raspberry Pi 5** with **64 GB+** microSD — see `spec-video-resolution.md`

- One PoE switch or PoE injector

- One IP camera

- One **4K HDMI** display (delayed coaching replay)

- One or more **~10″ Android tablets** on the Pi Wi‑Fi AP

The Raspberry Pi **always** provides a Wi‑Fi access point (`sport-assist-{serial_number}`). See `.cursor/spec-wifi-ap.md`.

There shall only ever be one camera connected to the system.

### Resolution tiers

```text

Camera RTSP ── 3840×2160 @ 25 fps (Ethernet)

       │

       ▼

Raspberry Pi 5

       ├── 4K rolling buffer ──► HDMI delayed replay (4K)

       └── 1080p rolling buffer ──► Wi‑Fi HLS (Android / iOS apps)

```

| Output | Resolution | Why |

|--------|------------|-----|

| **HDMI** | **3840 × 2160** | Large coach monitor; wired; full detail |

| **Wi‑Fi HLS (mobile apps)** | **1920 × 1080** | 10″ tablet; ~5 Mbps; multi-client friendly |

4K is **not** streamed to phones/tablets over Wi‑Fi in production. **WebRTC live over Wi‑Fi is not in v2** — coaches use **HDMI 4K** + Settings on a mobile device.

---

## Power Requirements

The camera shall receive power using Power over Ethernet (PoE) via a PoE switch or injector. The Raspberry Pi shall not power the camera.

---

## Network Requirements

Camera: **Ethernet only** (no Wi‑Fi).

Pi: **always-on Wi‑Fi AP** for tablets; optional Ethernet camera DHCP — see `.cursor/spec-network-dhcp.md`.

---

## Camera Naming

Hostname: `SportAssist-{serial_number}` (constant for installation lifetime).

---

## Camera Discovery

| Mode                           | Behaviour                                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Direct to Pi** (Pi DHCP on)  | Automatic at boot — Pi assigns camera IP; hostname `SportAssist-{serial}`                                    |
| **Customer LAN** (Pi DHCP off) | Settings **Search for camera** on customer Ethernet; match configured hostname rules; save credentials on Pi |

After credentials are set, Pi **auto-configures** camera streams via ONVIF (fallback ladder, GOP 25) — see `.cursor/spec-camera-stream-profiles.md`.

Hostname match: `SportAssist-*`, `sport-assist-*`, case-insensitive `sportassist` prefix. Detail: `.cursor/spec-camera-discovery.md`.

Pi runs discovery on **Ethernet**; Android triggers `POST /api/camera/discover` over Wi‑Fi AP only.

---

## Authentication

**Assign camera** (ONVIF, vendor-generic): the operator enters the camera’s **current** privileged login once. The Pi calls Device Management `CreateUsers` / `SetUser` to provision username **`sportassist`** with a **random** password, then stores only those assigned credentials in `/etc/sportassist/camera.env`. Implementation: `lib/camera_assign.py` → `provision_assigned_user()` — not UniView-specific APIs.

Keep the camera **super-user / admin** password private on the site. Do not ship it in git or public docs. Mobile apps **never** receive camera credentials.

---

## Video Requirements

RTSP ingest parameters, codec ladder, GOP, and ONVIF configure behaviour: **`.cursor/spec-camera-stream-profiles.md`**.

| Path             | Resolution                                     | Notes                |
| ---------------- | ---------------------------------------------- | -------------------- |
| 4K HDMI buffer   | Native main ingest (up to 3840×2160) @ ≥25 fps | Remux — no Pi encode |
| Wi‑Fi HLS buffer | 1920×1080 @ 25 fps from camera **sub stream**  | Remux — no Pi encode |

---

## HDMI Output

**Native ingest resolution** (up to **4K UHD**) delayed fullscreen replay — **`.cursor/spec-hdmi-output.md`**. User delay range and persistence: **`.cursor/spec-settings-page.md` §5`**.

---

## Coach live view (HDMI 4K — not WebRTC)

**Not in v2:** 1080p WebRTC or live-focus web pages over Wi‑Fi.

Coaches watch the pool on the **4K HDMI monitor** (delayed or live via Settings `HDMI_OUTPUT_MODE`). Lens, delay, and HDMI mode are adjusted from **Settings on a phone or tablet** (`/settings` in the mobile app or browser).

Must not interrupt the 4K HDMI pipeline or the 1080p Wi‑Fi HLS buffer.

---

## Lens Control

ONVIF zoom, focus, auto-focus, and **named presets** — `.cursor/spec-onvif-lens.md`.

---

## Camera Configuration (Commissioning)

1. Vendor Web UI — frame rate, streams, time, lighting, ONVIF/RTSP (see above).
2. Pi Settings — **Assign camera** with private admin credentials → `sportassist` user + hostname `SportAssistCam` + ONVIF stream ladder.
3. Confirm **4K / 25 fps** (or negotiated ladder) ingest and dual HLS buffers.

---

## Lighting Configuration

Permanent indoor day mode; disable IR, white light, and night modes.

---

## Web Streaming and Android Clients

| Client | Max resolution | Protocol | Endpoint |

|--------|----------------|----------|----------|

| **Mobile app replay** | **1080p** | HLS fMP4 | `GET /hls/live.m3u8` |
| **HDMI coach display** | **4K** | Delayed HLS + **cvlc** | `spec-hdmi-output.md` |

Android: ExoPlayer scrub of **20-minute 1080p** buffer; default **~14 s** behind live. No local buffer; no camera RTSP.

See `.cursor/spec-android-app.md`, `.cursor/spec-hls-replay-buffer.md`.

---

## Administration Interface

Web **`/settings`** (web login + optional settings-view unlock from `/etc/sportassist/web.env`): Ethernet mode, camera search + credentials, ONVIF stream auto-configuration, delay, lens/presets, buffer status. Wi‑Fi AP password set at construction only (`appliance.env`).

---

## Acceptance criteria

Integration checklist — detail lives in the linked specs (do not duplicate here):

| #   | Criterion                                         | Spec                                                               |
| --- | ------------------------------------------------- | ------------------------------------------------------------------ |
| 1   | ONVIF configure; ≥ 25 fps; GOP 25; codec fallback | `spec-camera-stream-profiles.md`                                   |
| 2   | Pi 4 GB+ / 64 GB SD; ~2.7 GB rolling buffers      | `spec-video-resolution.md`, `spec-hls-replay-buffer.md` §10        |
| 3   | HDMI delayed at main resolution; remux only       | `spec-hdmi-output.md`                                              |
| 4   | Android 1080p HLS over Wi‑Fi                      | `spec-mobile-clients.md` §4                                        |
| 5   | No 4K Wi‑Fi / no WebRTC                           | `constitution.md` §3.1                                             |
| 6   | Android thin client (no local buffer/credentials) | `spec-mobile-clients.md` §2                                        |
| 7   | Customer LAN camera search + remembered profile   | `spec-camera-discovery.md`                                         |
| 8   | AP, Ethernet, presets, delay persist              | `spec-wifi-ap.md`, `spec-network-dhcp.md`, `spec-settings-page.md` |

---

## Related Specifications

| Topic | Document |

|-------|----------|

| **Resolution tiers & storage** | `.cursor/spec-video-resolution.md` |

| Architecture | `.cursor/architecture-and-technical-spec.md` |

| Rolling buffers | `.cursor/spec-hls-replay-buffer.md` |

| HDMI 4K | `.cursor/spec-hdmi-output.md` |

| Android 1080p | `.cursor/spec-android-app.md` |

| HTTP / API | `.cursor/spec-api-endpoints.md` |

| Wi‑Fi AP | `.cursor/spec-wifi-ap.md` |

| Camera discovery (LAN) | `.cursor/spec-camera-discovery.md` |
| RTSP stream profiles | `.cursor/spec-camera-stream-profiles.md` |

| ONVIF | `.cursor/spec-onvif-lens.md` |

| Settings | `.cursor/spec-settings-page.md` |
