# Live Video Delay Replay System

An open-source, spec-driven sports replay platform for **Raspberry Pi 5**. It ingests RTSP video from IP cameras, maintains a configurable rolling replay buffer, outputs delayed video over **HDMI**, and serves authenticated 1080p HLS to **one tablet or browser client** (native app primary; `/replay` secondary) over an existing **LAN** or, where needed, its own **Wi‑Fi access point**.

Designed for unattended poolside, pitchside, and training-venue operation. Originally developed for **Board Diving**; the project is evolving into a **generic sports replay platform** suitable for multiple sports and coaching environments.

This project is open source under the [Apache License 2.0](LICENSE). Please read the [DISCLAIMER.md](DISCLAIMER.md) file before using or deploying the software.

**License:** [Apache 2.0](LICENSE) — Copyright © Emerson Warwick Limited (see [NOTICE](NOTICE))

**Contributions welcome** — please open a [pull request](CONTRIBUTING.md). Bug reports and ideas are appreciated via GitHub Issues and Discussions.

---

## Features

| Capability                | Description                                                                 |
| ------------------------- | --------------------------------------------------------------------------- |
| **Rolling replay buffer** | ~20 minutes of HLS/fMP4 on the Pi (4K main + 1080p Wi‑Fi tier)              |
| **Configurable delay**    | Wall-clock delay (default 14 s) for coach HDMI and client playback          |
| **HDMI output**           | Full-resolution delayed or live coach view on a 4K monitor                  |
| **LAN / client mode**     | Preferred where a venue network exists — Pi joins by Wi‑Fi or Ethernet      |
| **Wi‑Fi access point**    | Optional isolated AP on Pi built-in Wi‑Fi — sized for **one** replay client |
| **Web settings**          | Camera discovery, ONVIF stream setup, lens presets, delay, HDMI mode        |
| **Tablet / browser replay** | One authenticated 1080p HLS client (Android app primary; `/replay` secondary) |
| **Spec-driven**           | Behaviour defined in `.cursor/` specifications before code changes          |

---

## Architecture (summary)

```text
IP camera (RTSP + ONVIF, Ethernet)
        │
        ▼
Raspberry Pi 5 replay appliance
  • ffmpeg remux → dual rolling HLS buffers (no Pi transcode by default)
  • Flask web app — settings, HLS, API
  • cvlc / mpv — HDMI delayed or live output
        │
        ├── HDMI 4K monitor (coach)
        └── Wi‑Fi / LAN → one tablet or browser (1080p HLS, authenticated)
```

Full detail: [`.cursor/architecture-and-technical-spec.md`](.cursor/architecture-and-technical-spec.md)

> **Wi‑Fi capacity:** The Raspberry Pi 5 **built-in radio** (typically 2.4 GHz AP) has limited bandwidth. In practice it reliably supports **one** replay client scrubbing 1080p HLS — not multiple concurrent tablets. Coach video stays on **HDMI**; the tablet is for athlete review and settings. Multiple simultaneous Wi‑Fi replay clients are not a current product goal (see [ROADMAP.md](ROADMAP.md)).

> **Naming note:** Runtime paths and the Pi Linux user use the legacy **`sportassist`** prefix (`/etc/sportassist/`, `/home/sportassist/`, `User=sportassist`, `/usr/share/sportassist/`). A future release may rename these for the open-source project name — see [ROADMAP.md](ROADMAP.md) Phase 2.

---

## Repository layout

| Path                                             | Purpose                                                                 |
| ------------------------------------------------ | ----------------------------------------------------------------------- |
| [`.cursor/`](.cursor/)                           | **Specifications** — primary source of truth for behaviour              |
| [`pi-root/`](pi-root/)                           | Files deployed to `/` on the Pi (systemd, scripts, Flask app)           |
| [`config/`](config/)                             | Example per-unit env templates (`*.env.example` only in git)            |
| [`scripts/`](scripts/)                           | Build helpers (`pack-pi-root.sh`, `push-to-pi.sh`, …)                   |
| [`build-instructions.md`](build-instructions.md) | Manufacturing / install index (macOS & Windows)                         |
| [`requirements.txt`](requirements.txt)           | Install notes: apt Flask/zeep + pointer to pip packages                 |
| [`requirements-pip.txt`](requirements-pip.txt)   | Pip packages for Pi helpers (`onvif-zeep`, `WSDiscovery`)               |
| [`testing/`](testing/)                           | Manual test notes                                                       |

---

## Quick start

### Prerequisites

- Raspberry Pi 5 (4 GB RAM minimum; 8 GB recommended)
- 64 GB+ microSD (128 GB recommended), official 5 V 5 A USB-C PSU
- PoE-capable IP camera (ONVIF + RTSP) — see [`.cursor/NetworkCameraSpec.md`](.cursor/NetworkCameraSpec.md)
- Networking: prefer joining an existing venue **LAN** (Wi‑Fi client or Ethernet). For a self-hosted AP, use the **Raspberry Pi 5 built-in Wi‑Fi** — plan for **one** tablet or browser replay session
- 4K HDMI display (coach monitor)

### Camera commissioning (first project & credentials)

The first venue deployment used a **UNV (UniView) CCTV turret** camera (see the preferred model in [`.cursor/NetworkCameraSpec.md`](.cursor/NetworkCameraSpec.md)). Like most professional IP cameras, it has its **own vendor Web UI**. Commission that UI **before** assigning the camera to the Pi. Typical first-pass settings include:

- Frame rate set manually to **25 fps** (required for 1‑second GOP alignment with the HLS buffer)
- Encoding / resolution for the main and sub streams (4K + 1080p when available)
- Time zone and NTP so wall‑clock delay stays meaningful
- Indoor lighting profile — disable IR, white flood, and night modes when the venue is always lit
- Confirm **ONVIF** and **RTSP** are enabled and reachable on Ethernet
- Apply vendor firmware updates and check image quality before the Pi takes control

**Keep the camera super-user (admin) credentials private.** Do not commit them to git, put them in issues, or share them in public docs. Use that privileged login only briefly in Settings when you **Assign camera**. The Pi then creates a dedicated camera user (`sportassist`) with a random password for day-to-day RTSP/ONVIF, stores those credentials only in `/etc/sportassist/camera.env` on the appliance, and never sends them to mobile clients.

That assigned-user step uses standard **ONVIF Device Management** (`CreateUsers` / `SetUser`) — it is **vendor-generic**, not UniView-specific. Any ONVIF camera that allows remote user provisioning should work the same way; the UNV turret was the first camera validated in the field. Cameras that refuse ONVIF user creation will need a different commissioning path (operator may create an equivalent streaming user in the vendor Web UI first).

Full discovery / assign flow: [`.cursor/spec-camera-discovery.md`](.cursor/spec-camera-discovery.md).

### microSD wear (expect eventual replacement)

While the appliance is in delayed mode, it continuously records a **rolling video loop** (~20 minutes) onto the microSD card. Coaches and sports participants use that loop to scrub and review recent action, alongside the short wall‑clock delay shown on HDMI and client devices.

ffmpeg remuxes camera RTSP into dual HLS/fMP4 buffers under `/var/lib/sportassist/` (4K for HDMI, 1080p for Wi‑Fi). New **1‑second** segments are written and older ones deleted without pause. That sustained read/write cycle wears flash media; over time the card may fail and need replacing. Prefer a reputable high‑endurance microSD, and for heavy all‑day use consider a USB SSD for the buffer paths (optional; see [`.cursor/spec-video-resolution.md`](.cursor/spec-video-resolution.md)).

### Build the appliance

1. Read [`.cursor/constitution.md`](.cursor/constitution.md) and the [architecture spec](.cursor/architecture-and-technical-spec.md).
2. Follow [`build-instructions.md`](build-instructions.md) — choose **macOS** or **Windows** guide.
3. Copy `config/appliance.env.example` and `config/web.env.example` to per-unit files **outside git**; set unique serial, AP password, and web login credentials.
4. Flash Raspberry Pi OS Lite 64-bit, deploy `pi-root`, connect camera, verify replay.

### Access the unit

| Context     | URL / address                                                              |
| ----------- | -------------------------------------------------------------------------- |
| Venue LAN   | Device hostname or assigned address (preferred when joined to a LAN)       |
| Wi‑Fi AP    | SSID `sport-assist-{APPLIANCE_SERIAL}` (default AP `192.168.4.1`)          |
| Web UI      | Hostname on LAN, or `http://192.168.4.1` in AP mode                        |
| SSH         | `ssh sportassist@sport-assist.local` (if enabled)                          |

Log in with the credentials from your `web.env` (default username **`admin`** if unset).

Where a managed venue network is available, prefer **client LAN mode** (Settings → Network) over running the appliance as its own access point.

---

## Development philosophy

This project uses **Spec-Driven Development** (see [GitHub Spec Kit](https://github.com/github/spec-kit) for the general methodology):

1. **Specifications first** — functional changes begin with updates to the relevant `.cursor/spec-*.md` file.
2. **Code follows specs** — implementation must conform to published specifications.
3. **AI-assisted development** — tools such as [Cursor](https://cursor.com) can help you adapt this codebase to your hardware and venue (for example Wi‑Fi radio choice, network mode, or branding). This repository was developed with Cursor, which edits local files, runs git commands, and can deploy updates to the Raspberry Pi 5 over SSH. Generated changes must still match the published specs and architecture.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow and how to open a pull request.

---

## Documentation index

| Topic                  | Spec                                                                               |
| ---------------------- | ---------------------------------------------------------------------------------- |
| Architecture & systemd | [`architecture-and-technical-spec.md`](.cursor/architecture-and-technical-spec.md) |
| HTTP / HLS API         | [`spec-api-endpoints.md`](.cursor/spec-api-endpoints.md)                           |
| Settings & auth        | [`spec-settings-page.md`](.cursor/spec-settings-page.md)                           |
| Replay buffer          | [`spec-hls-replay-buffer.md`](.cursor/spec-hls-replay-buffer.md)                   |
| HDMI output            | [`spec-hdmi-output.md`](.cursor/spec-hdmi-output.md)                               |
| Mobile clients         | [`spec-mobile-clients.md`](.cursor/spec-mobile-clients.md)                         |
| Camera hardware        | [`NetworkCameraSpec.md`](.cursor/NetworkCameraSpec.md)                             |
| Document map           | [`constitution.md`](.cursor/constitution.md) §1                                    |

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features, rebranding work, and community priorities. Pull requests that advance roadmap items are especially welcome when they include matching spec updates.

---

## Contributing

We welcome contributions. **Please open pull requests** — small, focused PRs that update the relevant `.cursor/` spec and then the matching code are ideal.

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, PR checklist, and licensing. Issues that describe a venue problem (sport, hardware, network mode) help us prioritise.

The **source code remains open** under [Apache 2.0](LICENSE). Copyright © Emerson Warwick Limited — see [NOTICE](NOTICE).

### Hardware and commercial enquiry

**Emerson Warwick Limited** can help with hardware beyond the open-source software stack — for example **passive cooling** for the Raspberry Pi 5, a **water-resistant enclosure** for poolside or outdoor venues, or related mechanical and deployment design. If that is of interest, please open a GitHub Issue describing your venue and constraints, or contact Emerson Warwick Limited for commercial discussion. Installation, kits, and integration support may be offered separately from the open-source release.

---

## Security

The appliance is intended for unattended venue use. Soft-locking and credential hygiene are included in the shipped `pi-root` tree. Manufacturing steps that enable these controls are described in the build guides (for example **USB physical security** in `build-instructions-mac.md` §9.6 and the Windows guide equivalent).

Where a suitable network already exists, prefer joining a **client LAN** rather than operating the Pi as its own Wi‑Fi access point. An AI assistant such as [Cursor](https://cursor.com) can help you adapt the networking and Wi‑Fi code to match your site.

### Appliance hardening (code in `pi-root/`)

| Control | What it does | Where |
| ------- | ------------ | ----- |
| **USBGuard allowlist** | After install, only USB devices present when the policy was generated (typically Pi internal hubs) are allowed. Newly plugged devices are blocked by default (`ImplicitPolicyTarget=block`). | `ldrs-usb-hardening.service` → `ldrs-apply-usb-hardening.sh` / `ldrs-install-usbguard.sh`; policy under `/etc/usbguard/` |
| **Disable USB mass-storage boot** | Pi EEPROM `BOOT_ORDER=0xf1` so the unit boots from microSD only — USB stick boot is disabled. | `ldrs-disable-usb-boot.sh` |
| **Wi‑Fi for the access point** | The venue AP uses the **Raspberry Pi 5 built-in radio** (`brcmfmac`, typically `wlan0`). Plan for **one** authenticated replay client at a time. | `ldrs-wifi-ap.sh`, `ldrs-ensure-builtin-wifi.sh` |
| **WPA2 access point** | When AP mode is used, clients join a unit-specific SSID with a construction-time passphrase (`AP_PSK`). | `hostapd` template + `wifi-ap.env` |
| **Authenticated web and HLS** | Unauthenticated `/api/*` and `/hls/*` requests return **401**. Access requires a Flask session after web login; an optional second password unlocks Settings. | `server/app.py`, `web.env` |
| **SSH toggle** | SSH can be disabled from Settings once commissioning is complete. | `ldrs-set-ssh-enabled.sh` |
| **Least-privilege sudo** | The web service may invoke only a fixed whitelist of helper scripts via sudoers — not arbitrary root commands. | `etc/sudoers.d/sportassist-web` |
| **Camera credentials on the Pi only** | Assign creates a dedicated ONVIF/RTSP user with a random password stored in `camera.env`. Mobile apps never receive camera credentials or RTSP URLs. | `assign_camera.py`, Settings → Assign camera |

USB hardening does not depend on a Wi‑Fi dongle. Re-run with `LDRS_FORCE_USB_HARDENING=1` if you change USB peripherals that must remain allowed (see the build guide).

### Third-party networks

When the system is connected to any third-party network, whether by Wi‑Fi or Ethernet, responsibility for authorising that connection, controlling access to the network, and ensuring compliance with the network owner's IT and security policies rests with the user and the relevant network operator.

### Credential storage

Credentials are not stored in a single file. On the Pi they live under `/etc/sportassist/`; construction copies must be kept outside git.

| File on the Pi | Secrets / keys | Set when |
| -------------- | -------------- | -------- |
| **`camera.env`** | Assigned camera RTSP/ONVIF user (`CAMERA_USERNAME` / `CAMERA_PASSWORD`, usually `sportassist` plus a random password) | **Assign camera** in Settings |
| **`web.env`** | Web login (`SETTINGS_USERNAME` / `SETTINGS_PASSWORD`), optional settings-view password, Flask `FLASK_SECRET_KEY` | Construction (`config/web.env.example` → per-unit file) |
| **`appliance.env`** | Wi‑Fi AP passphrase (`AP_PSK`) and unit serial | Construction (`config/appliance.env.example` → per-unit file) |
| **`wifi-ap.env`** | Runtime AP SSID / PSK (merged from `appliance.env` at install or boot) | Construction / AP bring-up |

The camera’s own **admin / super-user** password is entered once for Assign and should remain in a private site record. It is not the day-to-day credential the Pi uses after Assign.

Keep the **Raspberry Pi Linux super-user and sudo credentials** secret. Do not put them in this repository, in committed env files, in issues, or in pull requests. Store them only in a private construction or venue record offline.

- Never commit per-unit secrets (`config/appliance-*.env`, `config/web-*.env`). Use the `.env.example` templates only.
- Rotate credentials if example files were ever committed with real passwords.
- Web login is required for HLS and API access in the current release.
- Mobile apps never store camera credentials.

---

## Privacy and GDPR

We believe **GDPR** and related data-protection expectations matter for sports venues where cameras may capture people training or competing. This project does not replace legal advice for a given club, school, or commercial operator, but the architecture is intended to support good practice:

- **Local by default** — video remains on the Pi’s rolling buffer and on authenticated clients on the venue network; there is no cloud upload path in the current design.
- **Short retention** — the rolling HLS window (about 20 minutes by default) limits how long imagery resides on the appliance before segments are overwritten.
- **Access control** — replay and API use require a web session; camera credentials never leave the Pi for mobile apps.
- **No product telemetry** — remote support or status export, if added later, is intended to remain **opt-in** and privacy-first (see [ROADMAP.md](ROADMAP.md)).
- **Operator responsibility** — venues should inform athletes and staff as appropriate, restrict physical and network access to the unit, use strong unique passwords per appliance, and disable SSH when remote administration is not required.

Deployers remain responsible for lawful basis, notices, and retention policies under the rules that apply to their organisation and country.

---

## Disclaimer

This project is provided for sports coaching, video replay, and educational purposes.

The software is provided **"AS IS"**, without warranties of any kind. Users are responsible for testing, validating, and safely deploying the software in their own environments.

Please read the full [DISCLAIMER.md](DISCLAIMER.md) before using this software.

---

## Acknowledgements

Built on Raspberry Pi OS, ffmpeg, Flask, ONVIF tooling, and VLC/mpv for HDMI playback. Evolved from earlier sport-focused replay prototypes; thank you to early field testers and coaches who shaped the delay-buffer architecture.
