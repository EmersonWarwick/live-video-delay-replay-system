# Spec: Mobile Clients (Android and iOS)

Normative specification for **native mobile apps** that consume the Pi replay appliance.

| Platform          | Language | Detail spec                   |
| ----------------- | -------- | ----------------------------- |
| **Android**       | Kotlin   | `.cursor/spec-android-app.md` |
| **iOS** (planned) | Swift    | `.cursor/spec-ios-app.md`     |

**Pi HTTP contract:** `.cursor/spec-api-endpoints.md`  
**Web login / session:** `.cursor/spec-settings-page.md` §3  
**Appliance architecture:** `.cursor/architecture-and-technical-spec.md`

---

## 1. Repository scope

Mobile apps are developed **outside** this repository (separate Android/iOS projects). Pi firmware and mobile apps may ship on different schedules — the Pi API is the integration contract.

---

## 2. Shared rules (both platforms)

1. Join Pi Wi‑Fi AP `sport-assist-{serial}`; base URL `http://192.168.4.1:8080`.
2. **`GET /device-info`** on startup (no auth). When `{ "device": "LDRS2", "status": "OK" }`, use v2 endpoints.
3. **`POST /settings/login`** with commissioning credentials; store **session cookie only**; attach to all HLS and API requests.
4. **Live** → `/hls/live.m3u8`; **Review** → `/hls/buffer.m3u8` + `GET /api/review`; **Presets** → `/presets` or `POST /presets/recall`; **Settings** → `/settings` (+ `/settings/unlock` when configured).
5. Talk **only** to Pi HTTP — never camera RTSP/ONVIF.
6. **Must not** create a local 20-minute buffer, persist web/camera passwords, or scan the customer LAN for cameras.
7. Coach poolside video is **HDMI 4K on the Pi** — not in the app (`spec-hdmi-output.md`).

---

## 3. Platform stack

| Concern        | Android                                    | iOS (planned)             |
| -------------- | ------------------------------------------ | ------------------------- |
| HLS playback   | Media3 / ExoPlayer (cookie-aware HTTP)     | AVPlayer                  |
| HTTP + cookies | OkHttp / Ktor `CookieJar`                  | `URLSession` cookie store |
| Presets UI     | WebView or native + `POST /presets/recall` | WKWebView or native       |
| Settings UI    | WebView or native mirror of `/settings`    | WKWebView or native       |
| Min OS         | Android 14+                                | TBD at iOS kick-off       |

---

## 4. Acceptance criteria (cross-platform)

1. `GET /device-info` → `LDRS2` / `OK` without web login.
2. Web login succeeds; `/hls/live.m3u8` plays with cookie on segment requests.
3. Review scrub and presets recall work after login.
4. Settings/camera APIs use settings-view unlock when configured; no passwords stored on device.
5. Multiple devices on one AP share one Pi buffer.
6. No `rtsp://` camera URLs in the app.

Platform-specific UI detail: `spec-android-app.md` §2–§3; iOS parity: `spec-ios-app.md`.
