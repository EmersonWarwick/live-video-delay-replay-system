# Spec: ONVIF Lens Control and Presets

Normative specification for motorised zoom/focus control and saved lens positions.

Related: `.cursor/NetworkCameraSpec.md`, `.cursor/spec-settings-page.md`.

---

## 1. Purpose

Allow operators to:

- **Zoom in / zoom out / stop zoom**
- **Focus near / focus far / stop focus**
- **Trigger auto-focus** (if supported by camera)
- **Save, recall, rename, and delete lens presets**
- **Persist presets** across reboots

Control plane: **ONVIF** (Profile S or T with PTZ/imaging support). Manufacturer SDKs are a fallback only if ONVIF PTZ is unavailable on the chosen camera.

---

## 2. Camera Requirements

Per `NetworkCameraSpec.md`:

- Motorised varifocal lens (2.7 mm – 13.5 mm on preferred UNV model).
- ONVIF PTZ or lens control namespace supported.
- Same credentials as RTSP (`camera.env`).

---

## 3. ONVIF Operations

### 3.1 Continuous move (while button held)

| UI action  | ONVIF operation                         | Stop condition          |
| ---------- | --------------------------------------- | ----------------------- |
| Zoom In    | `ContinuousMove` zoom positive velocity | Button release → `Stop` |
| Zoom Out   | `ContinuousMove` zoom negative velocity | Button release → `Stop` |
| Focus Near | `Move` or imaging focus near            | Button release → `Stop` |
| Focus Far  | `Move` or imaging focus far             | Button release → `Stop` |
| Auto Focus | `AutoFocus` or equivalent one-shot      | Completes on camera     |

Velocity values are implementation constants tuned during commissioning (document in code comments, not in user-facing spec).

### 3.2 Absolute position (presets)

When saving or recalling a preset:

1. **Read** current position via `GetStatus` / `GetConfiguration` (zoom and focus normalised 0.0–1.0 in `lens-presets.json`).
2. **Save** to preset entry.
3. **Recall** via `AbsoluteMove` (or `GotoPreset` if camera supports ONVIF presets natively — prefer native preset IDs if stable across reboots).

If the camera supports **native ONVIF presets**, the Pi may store `{ "onvifPresetToken": "..." }` instead of normalised floats.

---

## 4. Preset Storage

**File**: `/etc/sportassist/lens-presets.json`

**Schema**:

```json
{
  "version": 1,
  "presets": [
    {
      "id": "wide",
      "label": "Wide pool",
      "zoom": 0.0,
      "focus": 0.0,
      "onvifPresetToken": null
    },
    {
      "id": "board",
      "label": "Sport board",
      "zoom": 0.45,
      "focus": 0.32,
      "onvifPresetToken": null
    }
  ],
  "activePresetId": "wide"
}
```

**Rules**

- `id`: stable slug `[a-z0-9-]+`, max 32 chars.
- `label`: user-visible string, max 64 chars.
- Minimum **2** presets, maximum **8** presets (v2).
- Updates via helper `ldrs-set-lens-preset.sh` only (not direct web write to `/etc`).

---

## 5. Helper Script: `ldrs-onvif-lens.sh`

**Invocation examples**:

```bash
ldrs-onvif-lens.sh move zoom in
ldrs-onvif-lens.sh move zoom out
ldrs-onvif-lens.sh stop
ldrs-onvif-lens.sh autofocus
ldrs-onvif-lens.sh preset save <id>
ldrs-onvif-lens.sh preset recall <id>
ldrs-onvif-lens.sh preset delete <id>
```

**Behaviour**

- Reads camera IP from `/run/sportassist/camera.ip`.
- Reads credentials from `/etc/sportassist/camera.env`.
- Uses ONVIF library (Python `onvif-zeep` or equivalent) or direct SOAP.
- Exit non-zero on communication error; log without secrets.

---

## 6. Web UI Integration

See `spec-settings-page.md`:

- Lens controls on `/settings` (or dedicated `/settings/lens` if split later).
- **Press-and-hold** or **click-to-start / click-to-stop** for zoom/focus (must not leave motors running unattended).
- Preset dropdown + Save / Recall / Delete buttons.
- Active preset highlighted.

**API shape** (Flask routes — normative for v2):

| Method | Route                          | Action                    |
| ------ | ------------------------------ | ------------------------- |
| POST   | `/settings/lens/move`          | body: `axis`, `direction` |
| POST   | `/settings/lens/stop`          | stop all motion           |
| POST   | `/settings/lens/autofocus`     | one-shot AF               |
| POST   | `/settings/lens/preset/save`   | body: `id`, `label`       |
| POST   | `/settings/lens/preset/recall` | body: `id`                |
| POST   | `/settings/lens/preset/delete` | body: `id`                |

All routes invoke `sudo ldrs-onvif-lens.sh …` or a whitelisted subset.

---

## 7. Sudoers

```sudoers
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-onvif-lens.sh
sportassist ALL=(root) NOPASSWD: /usr/local/bin/ldrs-set-lens-preset.sh
```

No shell wildcards.

---

## 8. Safety

- Always send **Stop** on button release and on page unload (best-effort `navigator.sendBeacon`).
- Rate-limit move commands (max 10/s) to avoid flooding camera.
- If ONVIF session lost, show error on settings page; do not retry indefinitely.

---

## 9. Acceptance Criteria

1. Zoom and focus respond within 500 ms of UI action on LAN.
2. At least two named presets persist across reboot.
3. Recalled preset matches saved framing within operator-tolerable drift.
4. Motors stop when Stop is pressed or button released.
5. Credentials never appear in browser or logs.
