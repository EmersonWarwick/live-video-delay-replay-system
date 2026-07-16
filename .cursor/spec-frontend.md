# Spec: Web Frontend

Normative specification for the **browser UI** on the Pi.

**Athlete replay (primary):** `.cursor/spec-mobile-clients.md`  
**Web login:** `.cursor/spec-settings-page.md` §3  
**HTTP URLs:** `.cursor/spec-api-endpoints.md`

---

## 1. Browser routes

| Route | Behaviour |
|-------|-----------|
| `/` | Unauthenticated → `/settings/login`; authenticated → `/replay` |
| `/settings/login` | Username + password form |
| `/replay` | hls.js review/scrub on `/hls/buffer.m3u8` (after login) |
| `/web/index.html` | Static coach copy (served when logged in; not default `/`) |

---

## 2. Technology

Flask templates: `login.html`, `replay.html`, `settings.html`, `presets.html`. No SPA.

---

## 3. Acceptance criteria

1. Unauthenticated `/` redirects to login.
2. After login, `/replay` and `/presets` work.
3. No camera RTSP URLs in static HTML/JS.
