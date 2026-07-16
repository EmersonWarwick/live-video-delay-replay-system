# Spec: iOS Swift Replay App (Planned)

Future **iOS poolside client** — separate Swift project, not yet implemented.

**Behavioural parity:** `.cursor/spec-mobile-clients.md` and `.cursor/spec-android-app.md` §2 (screens).  
**HTTP contract:** `.cursor/spec-api-endpoints.md`

---

## iOS-specific stack

| Concern | Implementation |
|---------|----------------|
| HLS playback | AVPlayer / AVFoundation |
| HTTP + cookies | `URLSession` with shared cookie storage |
| Presets | WKWebView → `/presets` or native + `POST /presets/recall` |
| Settings | WKWebView → `/settings` |

---

## Acceptance criteria

Same as `.cursor/spec-mobile-clients.md` §4 when implemented.
