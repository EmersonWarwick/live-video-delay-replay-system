# Spec: Android Kotlin Replay App

Poolside **Android client** — separate Kotlin project (`AndroidAppMobile/` or successor).

**Shared rules:** `.cursor/spec-mobile-clients.md`  
**HTTP contract:** `.cursor/spec-api-endpoints.md`  
**Web login:** `.cursor/spec-settings-page.md` §3

---

## 1. User story

Connect to `sport-assist-{serial}` → open app → startup per `spec-mobile-clients.md` §2. Never talk to the camera directly.

---

## 2. Screens (Android-specific)

| Screen       | Implementation                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------- |
| **Live**     | ExoPlayer on `/hls/live.m3u8` — near delayed edge; poll `/api/review` or `/api/status` for `bufferWarming` |
| **Review**   | ExoPlayer on `/hls/buffer.m3u8`; timeline from `/api/review`; **Go to delayed live** → `liveEdgeTime`      |
| **Presets**  | WebView → `/presets` **or** native buttons + `POST /presets/recall`                                        |
| **Settings** | WebView → `/settings` or native mirror (preset CRUD here only)                                             |

**Playback:** 1080p HLS fMP4 only; mute; no local 20-minute download. Browser equivalent for Review: `GET /replay`.

---

## 3. Android-specific requirements

- ExoPlayer / Media3 must use a **cookie-aware** HTTP data source for HLS segments.
- Clear password fields from memory after login; retain cookie only.
- Recover gracefully from buffer warm-up and Wi‑Fi loss.

---

## 4. Acceptance criteria

See `.cursor/spec-mobile-clients.md` §4.
