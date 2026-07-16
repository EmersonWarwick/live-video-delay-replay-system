# Spec: Settings Page

Normative specification for `/settings`, the **`/presets`** lens page, **`/replay`**, and related Flask routes — live delay, HDMI, Ethernet mode, camera discovery, lens control, presets, datestamp overlay, and optional Wi‑Fi client mode.

Related: `.cursor/spec-onvif-lens.md`, `.cursor/spec-camera-discovery.md`, `.cursor/spec-camera-stream-profiles.md`, `.cursor/architecture-and-technical-spec.md`.

Implementation: **`server/app.py`**, templates **`settings.html`**, **`presets.html`**, **`login.html`**, **`replay.html`**.

---

## 1. Goals

- **Live delay**: set and remember **`LIVE_DELAY_SECONDS`** (integer seconds).
- **HDMI 4K output**: turn HDMI on/off; toggle **Delayed live to HDMI** vs **Show Live** (`HDMI_OUTPUT_MODE`).
- **Camera Ethernet mode**: turn Pi **Ethernet DHCP server on or off** (direct camera vs customer LAN).
- **Camera discovery & credentials**: search/find camera; enter username/password; Pi **interrogates via ONVIF**, **auto-configures** best stream profile (fallback ladder); persist on Pi.
- **Lens control**: zoom and focus **sliders with Send buttons**, manual/auto focus toggle, optional nudge moves via API.
- **Presets**: save, recall, rename, delete lens positions on **`/settings`**; **recall-only page** at **`/presets`** (web session required).
- **Video overlay**: ONVIF datestamp on/off when the camera supports it.
- **Web access control**: username/password web login for replay, HLS, presets, and APIs; optional second password for settings/camera pages; credentials in `/etc/sportassist/web.env`.
- **Safe privileged updates** via whitelisted helper scripts only.

### Non-goals

- Full NVR / recording management
- Arbitrary shell execution from web
- Storing camera password on Android (Pi only)
- Preset CRUD on the `/presets` page (recall only there)

---

## 2. Access Paths

| Client                      | URL                                        | Auth                                                                  |
| --------------------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| **Browser on Pi AP**        | `http://192.168.4.1:8080/settings`         | Web login + settings-view unlock when `SETTINGS_VIEW_PASSWORD` is set |
| **Pool deck / coaches**     | `http://<pi-ip>:8080/presets`              | Web login (same as HLS)                                               |
| **Tablet / browser replay** | `http://<pi-ip>:8080/replay`               | Web login                                                             |
| **Android Kotlin app**      | Native tabs + WebView for Settings/Presets | Web login; settings-view unlock for camera/lens CRUD                  |

All settings logic runs on the **Pi Flask app**. Mobile clients **must not** persist web or camera passwords locally; they **must** attach the Flask session cookie to HLS and API requests after login.

---

## 3. Web authentication

Almost every route requires a **web session**. Credentials live in `/etc/sportassist/web.env` — not in Flask source or mobile APKs.

### 3.1 Configuration file

**File**: `/etc/sportassist/web.env`

```bash
SETTINGS_USERNAME='admin'
SETTINGS_PASSWORD='ChangeMe-Before-Deploy-Settings'
SETTINGS_VIEW_PASSWORD='ChangeMe-Settings-View'
FLASK_SECRET_KEY=<random-hex-per-unit>
WEB_SESSION_TIMEOUT=28800
```

| Key                      | Required | Notes                                                                                                      |
| ------------------------ | -------- | ---------------------------------------------------------------------------------------------------------- |
| `SETTINGS_USERNAME`      | yes      | Web login username (default **`admin`**)                                                                   |
| `SETTINGS_PASSWORD`      | yes      | Web login password — replay, HLS, presets, status APIs (min 8 characters recommended)                      |
| `SETTINGS_VIEW_PASSWORD` | no       | When set, required to open `/settings`, camera APIs, lens control, and `/settings/network` after web login |
| `FLASK_SECRET_KEY`       | yes      | Flask session signing key — unique per unit at construction                                                |
| `WEB_SESSION_TIMEOUT`    | no       | Idle web session expiry in seconds; default **28800** (8 hours). Alias: `SETTINGS_SESSION_TIMEOUT`.        |

**Permissions**: `root:sportassist`, mode **`640`**.

**Template**: `config/web.env.example` → installed to `/etc/sportassist/web.env` at construction (alongside `appliance.env` for Wi‑Fi).

Web credentials are **independent** of Wi‑Fi AP password (`wifi-ap.env`) and camera credentials (`camera.env`).

### 3.2 Login flow

| Step | Behaviour                                                                                        |
| ---- | ------------------------------------------------------------------------------------------------ |
| 1    | Client opens any protected route without a valid session                                         |
| 2    | Flask redirects to **`GET /settings/login`** (or returns **401** JSON for `/api/*` and `/hls/*`) |
| 3    | User enters **`SETTINGS_USERNAME`** and **`SETTINGS_PASSWORD`**; **`POST /settings/login`**      |
| 4    | Pi compares credentials using constant-time comparison                                           |
| 5    | On success: Flask session cookie issued; default redirect to **`/replay`**                       |
| 6    | On failure: re-render login (“Incorrect username or password”)                                   |

**Logout**: **`POST /settings/logout`** or **`POST /logout`** clears session; redirect to login.

Session cookie: **HttpOnly**, **SameSite=Lax**. HTTPS not required on isolated AP (HTTP on `192.168.4.1`).

**Idle timeout**: After **`WEB_SESSION_TIMEOUT`** seconds without a protected request, the session is cleared. HLS segment requests do **not** refresh the idle timer (avoids cookie churn during playback).

**Settings-view unlock**: When `SETTINGS_VIEW_PASSWORD` is set, opening `/settings` or privileged APIs after web login redirects to **`/settings/unlock`** until the second password is entered.

**CSRF**: **Not required** on the isolated poolside AP (v2).

### 3.3 Route authentication

**Public** (no web session):

| Route                                         | Reason                                        |
| --------------------------------------------- | --------------------------------------------- |
| `GET /device-info`                            | Appliance generation probe for mobile startup |
| `GET/POST /settings/login`, `GET/POST /login` | Login form                                    |
| `OPTIONS` preflight                           | CORS                                          |

**Web session required** (401 JSON or redirect to login):

| Route pattern                           | Reason                      |
| --------------------------------------- | --------------------------- |
| `GET /`, `GET /replay`, `GET /review`   | Browser entry and replay    |
| `GET /hls/*`, `GET /hls-4k/*`           | HLS for mobile and browser  |
| `GET /api/status`, `GET /api/review`    | Status and review timeline  |
| `GET /presets`, `POST /presets/recall`  | Preset recall               |
| `GET /web/*`                            | Static coach landing assets |
| `POST /settings/logout`, `POST /logout` | End session                 |

**Web session + settings-view unlock** _(when `SETTINGS_VIEW_PASSWORD` is set)_:

| Route pattern                                                      | Reason                             |
| ------------------------------------------------------------------ | ---------------------------------- |
| `GET/POST /settings`, `GET /settings/network`                      | Settings forms                     |
| `POST /settings/hdmi/*`, `POST /settings/ssh/enabled`              | HDMI and SSH toggles               |
| `POST /api/camera/*`, `GET /api/camera`                            | Camera discovery and configuration |
| `GET/POST /api/network/*`                                          | Wi‑Fi client mode (see §7.5)       |
| `GET/POST /settings/lens/*`, `GET/POST /settings/camera/datestamp` | Lens and OSD                       |

Flask loads `web.env` at startup. If `SETTINGS_PASSWORD` is empty, refuse to start `ldrs-web.service` (fail closed).

### 3.4 Mobile and browser clients

- **Browser on AP**: log in once per session at `/settings/login`; cookie covers replay, HLS, presets, and status.
- **Mobile apps**: see `.cursor/spec-mobile-clients.md` §2 (session cookie only; no password persistence).

### 3.5 Changing credentials

Edit `/etc/sportassist/web.env` on the Pi, then restart `ldrs-web.service`. Routine settings UI does **not** expose password change.

---

## 4. Settings and privileged routes

Replay, HLS, status, presets, and `/device-info` routes: **`spec-api-endpoints.md`**.  
Auth column: **Yes** = web session; **(+ unlock)** = also requires settings-view unlock when `SETTINGS_VIEW_PASSWORD` is set.

| Method | Route                              | Auth           | Purpose                                                                  |
| ------ | ---------------------------------- | -------------- | ------------------------------------------------------------------------ |
| GET    | `/settings/login`, `/login`        | No             | Web login form                                                           |
| POST   | `/settings/login`, `/login`        | No             | Validate username/password; create session                               |
| POST   | `/settings/logout`, `/logout`      | Yes            | End web session                                                          |
| GET    | `/settings/unlock`                 | Yes            | Settings-view unlock form (when configured)                              |
| POST   | `/settings/unlock`                 | Yes            | Validate `SETTINGS_VIEW_PASSWORD`                                        |
| GET    | `/settings`                        | Yes (+ unlock) | Full settings form                                                       |
| POST   | `/settings`                        | Yes (+ unlock) | Save delay and Ethernet mode                                             |
| GET    | `/settings/network`                | Yes (+ unlock) | Wi‑Fi client mode UI                                                     |
| GET    | `/api/network/status`              | Yes (+ unlock) | Network status JSON                                                      |
| GET    | `/api/network/config`              | Yes (+ unlock) | Saved Wi‑Fi client config                                                |
| POST   | `/api/network/scan`                | Yes (+ unlock) | Scan for upstream Wi‑Fi networks                                         |
| POST   | `/api/network/save`                | Yes (+ unlock) | Save client Wi‑Fi credentials                                            |
| POST   | `/api/network/apply`               | Yes (+ unlock) | Apply saved client config                                                |
| POST   | `/api/network/switch-ap`           | Yes (+ unlock) | Return to AP mode                                                        |
| POST   | `/api/network/switch-client`       | Yes (+ unlock) | Switch to Wi‑Fi client mode                                              |
| POST   | `/api/network/forget`              | Yes (+ unlock) | Forget saved client network                                              |
| GET    | `/api/network/logs`                | Yes (+ unlock) | Network manager logs                                                     |
| POST   | `/settings/hdmi/mode`              | Yes (+ unlock) | Toggle HDMI delayed/live **immediately**                                 |
| POST   | `/settings/hdmi/enabled`           | Yes (+ unlock) | Turn HDMI output on/off **immediately**                                  |
| POST   | `/settings/ssh/enabled`            | Yes (+ unlock) | Enable/disable SSH                                                       |
| POST   | `/api/camera/discover`             | Yes (+ unlock) | Search LAN for cameras                                                   |
| POST   | `/api/camera/test`                 | Yes (+ unlock) | Test ONVIF login before assign                                           |
| POST   | `/api/camera/streams`              | Yes (+ unlock) | ONVIF interrogate + configure camera streams                             |
| GET    | `/api/camera`                      | Yes (+ unlock) | Current camera + configured streams (no password)                        |
| POST   | `/api/camera/assign`               | Yes (+ unlock) | Assign camera — factory login → `sportassist` + generated password       |
| POST   | `/api/camera`                      | Yes (+ unlock) | Legacy save camera credentials; auto-configure streams                   |
| POST   | `/api/camera/clear`                | Yes (+ unlock) | Clear saved camera configuration                                         |
| GET    | `/settings/lens/position`          | Yes (+ unlock) | Read zoom/focus/ranges/autofocus state                                   |
| POST   | `/settings/lens/position`          | Yes (+ unlock) | Set zoom and/or focus (slider Send)                                      |
| POST   | `/settings/lens/move`              | Yes (+ unlock) | Nudge zoom or focus one step                                             |
| POST   | `/settings/lens/stop`              | Yes (+ unlock) | Stop PTZ/imaging motion                                                  |
| POST   | `/settings/lens/autofocus`         | Yes (+ unlock) | Set auto/manual focus (`{ enabled: true/false }`) or trigger one-shot AF |
| GET    | `/settings/camera/datestamp`       | Yes (+ unlock) | Read datestamp overlay state                                             |
| POST   | `/settings/camera/datestamp`       | Yes (+ unlock) | Turn camera datestamp on/off                                             |
| GET    | `/settings/lens/preset/list-onvif` | Yes (+ unlock) | List camera ONVIF presets (if supported)                                 |
| POST   | `/settings/lens/preset/save`       | Yes (+ unlock) | Save/update preset (`preset save-onvif` with local fallback)             |
| POST   | `/settings/lens/preset/recall`     | Yes (+ unlock) | Recall preset                                                            |
| POST   | `/settings/lens/preset/delete`     | Yes (+ unlock) | Remove preset                                                            |

All JSON responses include CORS headers per `spec-api-endpoints.md` §2.3.

Implementation: **Flask** (`server/app.py`). Lens and preset moves invoke **`ldrs-onvif-lens.sh`** via `sudo` (50 s timeout for recall/position).

---

## 5. Live delay

### 5.1 UI

- Control: integer input on **Save settings** form.
- Range: **`delay_min`–`delay_max`** inclusive — **`delay_min`** is **pipeline latency** (`PIPELINE_LATENCY_SECONDS`, default **3**); **`delay_max`** is **60** (default live delay **14**).
- Hint: explains HDMI wall-clock delay vs tablet HLS edge offset (~pipeline latency before delayed edge).

### 5.2 Validation

- Required on save.
- Integer only; reject out-of-range values (minimum cannot be below ingest pipeline latency).

### 5.3 Persistence

**File**: `/etc/sportassist/system.env`

```bash
LIVE_DELAY_SECONDS=14
PIPELINE_LATENCY_SECONDS=3
# HDMI_PLAYBACK_BIAS_SECONDS=0   # optional fine-tune
```

**Helper**: `/usr/local/bin/ldrs-set-delay.sh <seconds>`

### 5.4 Read-back on GET

Parse `LIVE_DELAY_SECONDS`, `PIPELINE_LATENCY_SECONDS` from `system.env`; expose `delay_min`, `delay_max`, `pipeline_latency` to template.

---

## 6. HDMI 4K output

Controls how the **poolside HDMI monitor** (3840×2160) tracks the 4K HLS buffer. See `.cursor/spec-hdmi-output.md`.

### 6.1 UI

Section heading: **HDMI 4K output**

**HDMI on/off** switch — `POST /settings/hdmi/enabled` stops both HDMI services when off; re-activates saved mode when on.

**Show Live** switch (when HDMI on) — labels:

| Position   | Label                                  | `HDMI_OUTPUT_MODE` |
| ---------- | -------------------------------------- | ------------------ |
| Off / left | **Delayed** (implicit — Show Live off) | `delayed`          |
| On / right | **Show Live**                          | `live`             |

Toggle calls `POST /settings/hdmi/mode` **on change** — does not wait for **Save settings**.

### 6.2 Persistence

**File**: `/etc/sportassist/system.env`

```bash
HDMI_ENABLED=1
HDMI_OUTPUT_MODE=delayed
```

**Helpers**: `ldrs-set-hdmi-mode.sh`, `ldrs-set-hdmi-enabled.sh`, `ldrs-hdmi-activate.sh`

---

## 7. Camera Ethernet mode

Controls whether the Pi runs a **DHCP server on `eth0`** for the IP camera.

### 7.1 UI

Section heading: **Camera Ethernet**

Radio buttons:

| Label            | Value    | When to use                  |
| ---------------- | -------- | ---------------------------- |
| **Direct to Pi** | `direct` | Camera on PoE Ethernet to Pi |
| **Customer LAN** | `lan`    | Camera on site/building LAN  |

Saved via **Save settings** (`POST /settings`).

### 7.2 Persistence

**File**: `/etc/sportassist/network.env`

```bash
ETH_CAMERA_DHCP=1   # direct
ETH_CAMERA_DHCP=0   # customer LAN
```

**Helper**: `/usr/local/bin/ldrs-set-eth-camera-dhcp.sh enable|disable`

---

## 7.5 Wi‑Fi client mode (optional)

**Route**: `GET /settings/network`  
**API**: `/api/network/*` (status, config, scan, save, apply, switch-ap, switch-client, forget, logs)

Allows the Pi to join an upstream Wi‑Fi network as a client (via `ldrs-wifi-network.service` / NetworkManager) instead of—or in transition from—the poolside AP. Requires **web session** and **settings-view unlock** when configured.

Implementation: `lib/network/` Python package, `ldrs-wifi-network-cli.sh`, template `network_settings.html`.

Production poolside units normally stay in **AP mode** (`ldrs-wifi-ap.service`). Document for bench/service use only unless product enables client mode in the field.

---

## 8. Camera discovery, credentials, and ONVIF

### 8.1 Direct to Pi (`ETH_CAMERA_DHCP=1`)

- Pi reads dnsmasq lease → hostname + IP on Settings.
- **Refresh camera** → `POST /api/camera/discover`.
- Factory username/password → **Test login** → **Assign camera**.

### 8.2 Customer LAN (`ETH_CAMERA_DHCP=0`)

- **Search for camera** → radio list → factory login → **Assign camera**.

### 8.3 Shared UI (both modes)

| Control                           | Behaviour                                                                        |
| --------------------------------- | -------------------------------------------------------------------------------- |
| Hostname                          | Read-only after assign (`SportAssistCam`)                                        |
| IP                                | From discovery; read-only when assigned                                          |
| **Test login**                    | `POST /api/camera/test`                                                          |
| **Assign camera**                 | `POST /api/camera/assign`                                                        |
| Assigned state                    | Read-only hostname, IP, username `sportassist`, **password visible** on Settings |
| **Re-configure streams**          | `POST /api/camera/streams`                                                       |
| **Search / Refresh / swap panel** | Discover + assign replacement camera                                             |

### 8.4 Stream auto-configuration

After assign: `ldrs-assign-camera.sh` → ONVIF user provision, hostname, `configure_streams.py`, ladder (Ultra 265 → H.265 → H.264; resolution fallback 4K → 1440p → 1080p @ 25 fps).

### 8.5 Read-back

- `GET /api/camera` — hostname, IP, username, ingest fields, sub-stream; **never** password.
- Settings template shows assigned password server-rendered when `camera_assigned`.

---

## 9. Video overlay (datestamp)

Section heading: **Video overlay**

| Control                       | Behaviour                                                                    |
| ----------------------------- | ---------------------------------------------------------------------------- |
| **Datestamp off / on** switch | `GET/POST /settings/camera/datestamp` via **`ldrs-onvif-osd.sh`**            |
| Unsupported camera            | Switch disabled; hint “This camera does not expose ONVIF datestamp control.” |

When supported, toggling off caches OSD config to `/etc/sportassist/datestamp-osd-cache.json` for restore.

Requires settings auth. Implementation: `onvif_osd.py`.

---

## 10. Lens controls UI

Per `spec-onvif-lens.md` and current **`settings.html`**:

### 10.1 Sliders (primary UI)

| Control                     | Behaviour                                                                                             |
| --------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Zoom** slider + **Send**  | `POST /settings/lens/position` with `{ zoom }` only — **PTZ AbsoluteMove (zoom-only)** on UNV turrets |
| **Focus** slider + **Send** | `POST /settings/lens/position` with `{ focus }` only — ONVIF imaging focus move                       |
| **Get ranges**              | `GET /settings/lens/position` — reads zoom/focus limits and enables sliders                           |
| **Refresh position**        | `GET /settings/lens/position` — updates slider positions from camera                                  |

Zoom Send does **not** send focus or autofocus commands. Hint: camera may still refocus if auto focus is on.

### 10.2 Manual / auto focus

| Control                              | Behaviour                                                      |
| ------------------------------------ | -------------------------------------------------------------- |
| **Manual focus / Auto focus** switch | `POST /settings/lens/autofocus` with `{ enabled: true/false }` |

### 10.3 Optional nudge API

`POST /settings/lens/move` with `{ axis: "zoom"|"focus", direction: "in"|"out" }` — single step per request (not used by main slider UI).

### 10.4 Timeouts

Client requests use **55 s** timeout for lens position and preset recall; server subprocess timeout **50 s**. Errors include `lens_timeout`, `zoom_move_failed`, `focus_mode_manual_failed`, etc.

---

## 11. Presets

**Storage**: `/etc/sportassist/lens-presets.json`

```json
{
  "activePresetId": "wide",
  "presets": [
    {
      "id": "wide",
      "label": "Wide pool",
      "zoom": 0.0,
      "focus": 0.5,
      "onvifPresetToken": null
    }
  ]
}
```

| Field              | Notes                                                                                                                            |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `id`               | Stable slug; max 8 presets                                                                                                       |
| `label`            | User-visible name                                                                                                                |
| `zoom`             | Normalised PTZ zoom (0.0–1.0) — **recall uses this**                                                                             |
| `focus`            | Display/metadata; **not applied on recall** for UNV IPC3638 (zoom-only recall avoids lens creep)                                 |
| `onvifPresetToken` | Used when camera supports ONVIF `GetPresets`/`SetPreset`/`GotoPreset`; **null** on UNV IPC3638 (optional action not implemented) |

### 11.1 Settings page — Presets section

| Control                  | Behaviour                                                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Preset buttons** (row) | Tap to recall — `POST /settings/lens/preset/recall`                                                                                                                 |
| **Update selected**      | Save current PTZ zoom to preset — `POST /settings/lens/preset/save` → `preset save-onvif` (falls back to **local zoom save** when camera has no ONVIF preset slots) |
| **Save as new**          | New preset with label from text field                                                                                                                               |
| **Delete selected**      | `POST /settings/lens/preset/delete` (confirm dialog)                                                                                                                |

Active preset button highlighted green. After save, page reloads to refresh button list.

**Recall behaviour** (`onvif_lens.py` → `apply_preset_to_camera`):

1. If `onvifPresetToken` **and** camera supports ONVIF presets → **`GotoPreset`** only, then stop.
2. Else → **`apply_lens_zoom`** to stored `zoom` only — **no focus/imaging commands**.

### 11.2 Preset recall page — `/presets`

**Template**: `presets.html` — **web session required** (same login as HLS).

| Element           | Behaviour                                                  |
| ----------------- | ---------------------------------------------------------- |
| Column of buttons | One per preset in `lens-presets.json`                      |
| Tap button        | `POST /presets/recall` with `{ id }`                       |
| Active preset     | Green highlight                                            |
| Messages          | **Errors only** (no “Moving to…” or “At …” success toasts) |
| CRUD              | **None** — recall only                                     |

Suitable for pool-deck phones/tablets on the AP after web login — share the unit’s web username/password with coaches, not the optional settings-view password unless they need CRUD on `/settings`.

**Mobile apps:** **Presets** tab — `WebView` / `WKWebView` loading this page, or native buttons calling `POST /presets/recall`. See `.cursor/spec-mobile-clients.md`, `.cursor/spec-android-app.md` §2.

## 12. Camera status (read-only)

Display on settings page **Status** card:

| Field                             | Source                                            |
| --------------------------------- | ------------------------------------------------- |
| Wi‑Fi SSID                        | `wifi-ap.env` → `AP_SSID`                         |
| Live delay                        | `system.env` → `LIVE_DELAY_SECONDS`               |
| HDMI mode                         | `system.env` → `HDMI_ENABLED`, `HDMI_OUTPUT_MODE` |
| Buffer / camera                   | `GET /api/status` via `build_status()`            |
| Hostname, IP, ingest, credentials | `camera.env` (password shown when assigned)       |
| Ethernet mode                     | `network.env` → `ETH_CAMERA_DHCP`                 |
| Active preset                     | `lens-presets.json` → `activePresetId`            |

---

## 13. Privileged helpers and sudoers

**File**: `/etc/sudoers.d/sportassist-web`

```sudoers
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-delay.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-hdmi-mode.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-hdmi-enabled.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-hdmi-activate.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-eth-camera-dhcp.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-discover-cameras.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-probe-camera-streams.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-configure-camera-streams.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-test-camera-auth.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-camera-config.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-assign-camera.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-onvif-lens.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-lens-preset.sh
```

Lens and preset operations use **`ldrs-onvif-lens.sh`** → `onvif_lens.py`. Datestamp uses **`ldrs-onvif-osd.sh`** → `onvif_osd.py` (invoked with `sudo` from Flask).

Web app user: **`sportassist`**. Never run Flask as root.

---

## 14. Error handling

- Validation errors: re-render settings with red message; no service changes.
- Helper non-zero exit: generic or structured JSON error; no stderr dump to browser.
- ONVIF timeout: `lens_timeout`, `configure_timeout`, etc.
- Lens: `zoom_move_failed`, `focus_move_failed`, `focus_mode_manual_failed`, `goto_preset_failed`.
- Public `/presets`: error banner only on failure; success is silent (active button state only).

---

## 15. Security model

See §3. Poolside AP only; never log passwords. `ldrs-web` fails closed if `SETTINGS_PASSWORD` is unset.

---

## 16. Acceptance criteria

1. Delay, HDMI, and Ethernet mode changes persist and apply as documented in §5–§7.
2. Camera assign + ONVIF stream configure works in both Ethernet modes.
3. Lens sliders and presets behave per §10–§11.
4. Auth behaviour matches §3 (401/403/redirect as specified).
5. `/presets` recall works after web login.
