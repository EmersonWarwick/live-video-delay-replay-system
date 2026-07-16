# Development Roadmap

This roadmap describes planned direction for **Live Video Delay Replay System**. It is not a commitment schedule — priorities may shift based on community feedback and field testing.

**Current release focus:** generic sports language in specs/UI, Phase 2 branding choices, and field hardening.

**Repository:** [github.com/EmersonWarwick/live-video-delay-replay-system](https://github.com/EmersonWarwick/live-video-delay-replay-system) (public). **Pull requests welcome.** Community PRs that fix specs/code mismatch, improve build guides, or advance the items below are especially helpful. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Near-term polish

- Final spec pass — generic sports language; accurate vs shipped code (UI still uses “Sport Assist”)
- Open Issues for external contributors; default branch protection

---

## Phase 2 — Platform generalisation

Goal: reduce sport-specific branding while preserving stable runtime behaviour.

| Item                       | Description                                                                                       |
| -------------------------- | ------------------------------------------------------------------------------------------------- |
| **User-facing branding**   | Settings UI titles, idle splash, logo assets — configurable or neutral “Replay System” branding   |
| **SSID / hostname prefix** | Evaluate `replay-{serial}` vs legacy `sport-assist-{serial}` (breaking change — spec + migration) |
| **Runtime paths**          | Evaluate renaming `/etc/sportassist/` → `/etc/lvdrs/` (large migration; low priority)             |
| **Pi user account**        | Evaluate `replay` system user vs legacy `sportassist`                                             |
| **Documentation**          | Sport-agnostic examples (swimming, athletics, team sports)                                        |

---

## Phase 3 — Client ecosystem

Goal: a reliable **single-tablet** replay experience on venue Wi‑Fi (native app primary; browser `/replay` secondary).

| Item                     | Notes                                                     |
| ------------------------ | --------------------------------------------------------- |
| **Android app (Kotlin)** | External repo — ExoPlayer thin client per `spec-android-app.md` (primary) |
| **iOS app (Swift)**      | Parity with Android per `spec-ios-app.md`                 |

---

## Phase 4 — Network & deployment

Goal: flexible venue networking without sacrificing AP simplicity.

| Item                       | Description                                                                   |
| -------------------------- | ----------------------------------------------------------------------------- |
| **Headless commissioning** | QR or label-based default URL; optional first-boot wizard spec                |
| **Remote support hooks**   | Optional telemetry/status export (privacy-first, opt-in)                      |

---

## Phase 5 — Reliability & operations

Goal: unattended operation at sports venues.

| Item                        | Description                                                              |
| --------------------------- | ------------------------------------------------------------------------ |
| **Broader auto-recovery**   | ffmpeg stall, HDMI player restart, fuller recovery matrix                |
| **Structured service logs** | Rotating logs under `/var/log/sportassist/` (path may change in Phase 2) |
| **Health endpoint**         | Extend `/api/status` for NOC/monitoring integrations                     |
| **Soak & regression suite** | Expand `testing/`; optional CI for Python unit tests                     |

---

## Phase 6 — Camera & video flexibility

Goal: support more cameras and venues without Pi transcode.

| Item                         | Description                                                   |
| ---------------------------- | ------------------------------------------------------------- |
| **ONVIF profile ladder**     | Documented fallback steps in `spec-camera-stream-profiles.md` |
| **Additional camera models** | Community-tested devices beyond UNV reference                 |
| **1080p-only venues**        | Single-stream mode when 4K unnecessary                        |
| **Optional audio**           | Spec amendment required (currently video-only invariant)      |

---

## Explicit non-goals (v2)

These remain out of scope unless a future major version amends `constitution.md` §3.1:

- WebRTC low-latency live over Wi‑Fi
- Unauthenticated public HLS
- Per-client local 20-minute recording on tablets
- Direct camera RTSP from mobile apps
- **Multiple concurrent Wi‑Fi replay clients** on the Pi AP (built-in radio is sized for one 1080p scrub session)

Coach near-live video: **HDMI** (delayed or live toggle). Athlete review: **one authenticated** 1080p HLS client on the Pi buffer (native app primary; browser `/replay` secondary).

---

## How to influence the roadmap

1. Open a GitHub Issue or Discussion with the **problem** (venue, sport, hardware).
2. Propose a **spec change** in `.cursor/` before implementation.
3. For large features, start a Discussion thread before coding.
4. **Open a pull request** when you have a concrete fix or improvement — even a small docs or test PR moves the project forward.

Commercial installation, hardware bundles, and paid support are expected to fund ongoing maintenance; the **source code stays open**.

---

## Version labelling (informal)

| Label          | Meaning                                                     |
| -------------- | ----------------------------------------------------------- |
| **v2 / LDRS2** | Current appliance generation (`GET /device-info` → `LDRS2`) |
| **LVDRS**      | Open-source project name (Live Video Delay Replay System)   |

Device generation identifiers may remain `LDRS2` until a breaking API/appliance generation is specified.
