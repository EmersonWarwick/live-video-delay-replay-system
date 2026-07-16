# pi-root — Raspberry Pi 5 runtime layout

This tree is extracted to `/` on the Pi during installation (see `build-instructions-mac.md` or `build-instructions-pc.md`).

| Path                                                 | Purpose                                                       |
| ---------------------------------------------------- | ------------------------------------------------------------- |
| `etc/sportassist/*.env`                              | Runtime configuration (merged from `config/` at construction) |
| `etc/sportassist/lens-presets.json`                  | Factory lens preset labels                                    |
| `etc/hostapd/hostapd-sportassist.conf`               | Wi‑Fi AP template (SSID/PSK substituted at boot)              |
| `etc/dnsmasq.d/ldrs-camera-eth.conf`                 | DHCP for camera on `eth0` (direct mode)                       |
| _(runtime)_ `etc/dnsmasq.d/sportassist-wifi-ap.conf` | Written by `ldrs-wifi-ap.sh` when AP is active — not shipped  |
| `etc/sudoers.d/sportassist-web`                      | Passwordless sudo for whitelisted helper scripts              |
| `etc/systemd/system/ldrs-*.service`                  | Systemd units                                                 |
| `usr/local/bin/ldrs-*.sh`                            | Privileged helper and service scripts                         |
| `usr/local/bin/ldrs-fix-pi-root-ownership.sh`        | Run after every `pi-root` tarball extract (Mac uid 501 fix)   |
| `usr/local/bin/ldrs-diagnose-ap.sh`                  | Wi‑Fi AP diagnostics when hostapd fails                       |
| `usr/share/sportassist/`                         | Idle splash assets (`SportAssistLogo.png`, `SportAssistIdle.ass`) |
| `home/sportassist/dev/ldrs/lib/`                     | Python ONVIF helpers, discovery, configure                    |
| `home/sportassist/dev/ldrs/server/`                  | Flask web app (`app.py`, `templates/`)                        |
| `home/sportassist/dev/ldrs/web/`                     | Coach landing page (`index.html`)                             |
| `var/lib/sportassist/`                               | Placeholder; HLS buffers created at install                   |

> Legacy path prefix `sportassist` — see [ROADMAP.md](../ROADMAP.md) Phase 2 for planned renaming.

Specs: `.cursor/architecture-and-technical-spec.md`

**Web access:** `spec-settings-page.md` §3.

**Build PC helpers** (repo `scripts/`): `pack-pi-root.sh`, `push-to-pi.sh` — see `build-instructions-mac.md` §7 and §12.
