# Spec: Wi‑Fi Access Point (Always On)

Normative specification for the poolside Wi‑Fi AP on the Raspberry Pi 5.

Related: `.cursor/architecture-and-technical-spec.md`, `.cursor/spec-network-dhcp.md`, `config/appliance.env.example`.

---

## 1. Purpose

The Pi **always** runs a Wi‑Fi access point at boot so coaches and athletes can connect phones and tablets without relying on site Wi‑Fi.

The AP provides access to:

- Web UI and settings (`:8080`)
- **HLS replay buffer** (`GET /hls/live.m3u8`) — **Android / iOS apps only** (not a browser product)
- Status API (`GET /api/status`)
- Settings (`/settings`)

**Primary poolside replay UX**: Android Kotlin / iOS Swift native apps — see `.cursor/spec-mobile-clients.md`.  
**Coach video**: HDMI 4K on the Pi — not WebRTC over Wi‑Fi.

The **camera never uses Wi‑Fi** — camera traffic is Ethernet only.

---

## 2. Requirements

| Requirement                | Rule                                                                    |
| -------------------------- | ----------------------------------------------------------------------- |
| AP at boot                 | **Always enabled** — no settings toggle to disable AP in v2             |
| SSID format                | `sport-assist-{serial_number}`                                          |
| Password                   | WPA2-PSK, set at construction/commissioning                             |
| Interface                  | Raspberry Pi **built-in** Wi‑Fi (`brcmfmac`, typically `wlan0`) |
| Client DHCP                | Pi runs dnsmasq on `wlan0` for connected clients                        |
| Isolation from camera DHCP | AP DHCP on `wlan0` is **independent** of Ethernet camera DHCP on `eth0` |

**Example SSID**: `sport-assist-ABC123456`

---

## 3. Configuration Files

### 3.1 Construction / development (project repo)

**Path**: `config/appliance.env.example`  
Copied and customised per unit during build → installed as `/etc/sportassist/appliance.env`.

| Key                | Example                 | Purpose                          |
| ------------------ | ----------------------- | -------------------------------- |
| `APPLIANCE_SERIAL` | `ABC123456`             | Unique unit serial; used in SSID |
| `AP_PSK`           | `D1v1ng-P00l.K9mAs5ist` | Wi‑Fi password (WPA2)            |
| `AP_COUNTRY_CODE`  | `GB`                    | Regulatory domain                |

Operators edit this file **before imaging or first deploy**. It is not changed from the routine settings page (password rotation is a future amendment).

### 3.2 Runtime (on Pi)

**Path**: `/etc/sportassist/wifi-ap.env`

| Key                   | Example                  | Purpose                                                 |
| --------------------- | ------------------------ | ------------------------------------------------------- |
| `APPLIANCE_SERIAL`    | `ABC123456`              | From appliance.env                                      |
| `AP_SSID`             | `sport-assist-ABC123456` | Computed at install: `sport-assist-${APPLIANCE_SERIAL}` |
| `AP_PSK`              | _(secret)_               | From appliance.env                                      |
| `AP_INTERFACE`        | `wlan0`                  | Wi‑Fi interface                                         |
| `AP_COUNTRY_CODE`     | `GB`                     |                                                         |
| `AP_CHANNEL`          | `6`                      | 2.4 GHz channel                                         |
| `AP_ADDRESS`          | `192.168.4.1`            | Pi address on AP interface                              |
| `AP_NETMASK`          | `255.255.255.0`          |                                                         |
| `AP_DHCP_RANGE_START` | `192.168.4.100`          | Client lease range                                      |
| `AP_DHCP_RANGE_END`   | `192.168.4.150`          |                                                         |
| `AP_DHCP_LEASE_TIME`  | `24h`                    |                                                         |

**Rules**

- `AP_SSID` must match `sport-assist-{APPLIANCE_SERIAL}` unless a spec amendment documents a site override.
- `wifi-ap.env` permissions: `root:root`, mode `600` (contains `AP_PSK`).
- Do not duplicate AP settings in `network.env` or systemd units.

### 3.3 hostapd / dnsmasq templates (project)

Installed from `pi-root/`:

- `/etc/hostapd/hostapd-sportassist.conf` — SSID and passphrase substituted from `wifi-ap.env` at install or via `ldrs-wifi-ap.sh`.
- `/etc/dnsmasq.d/sportassist-wifi-ap.conf` — **created at runtime** by `ldrs-wifi-ap.sh` when AP is active; removed when AP stops or client Wi‑Fi connects.

---

## 4. Service: `ldrs-wifi-ap.service`

**Type**: oneshot, `RemainAfterExit=yes`  
**Exec**: `/usr/local/bin/ldrs-wifi-ap.sh`  
**Order**: `After=network.target`, before `ldrs-web.service`

**Script behaviour**

1. Source `/etc/sportassist/wifi-ap.env`.
2. Ensure onboard Wi‑Fi is not disabled (`ldrs-ensure-builtin-wifi.sh` removes `dtoverlay=disable-wifi-pi5` if present).
3. Resolve `AP_INTERFACE` (prefer `brcmfmac`; default `wlan0`).
4. Set Wi‑Fi country code (`raspi-config nonint do_wifi_country`).
5. Unblock Wi‑Fi radio (`rfkill unblock wifi`).
6. Configure static IP on `AP_INTERFACE`.
7. Write/update hostapd config with `AP_SSID` and `AP_PSK`.
8. Start `hostapd` and dnsmasq for AP scope on the built-in radio.
9. Exit non-zero on failure (journald logs; systemd may retry per unit policy).

AP startup is **unconditional** — no `AP_ENABLED=0` switch in v2.

---

## 5. Client Experience

1. User joins Wi‑Fi `sport-assist-{serial_number}` with the configured password.
2. Device receives DHCP address in `192.168.4.100`–`192.168.4.150`.
3. User opens `http://192.168.4.1:8080/` (or `http://sport-assist.local:8080/` if mDNS is enabled on AP — optional).

Default hostname for the Pi on the AP network: **`sport-assist`** (build instructions).

---

## 6. Security

- WPA2-PSK only; no open AP.
- Password set at construction via `config/appliance.env` → not exposed on settings page.
- AP is the primary access control for web UI (same model as MobileReplaySystem).
- Do not log `AP_PSK` in journald.

---

## 7. Coexistence with Ethernet Camera DHCP

**Camera ingest is always Ethernet (`eth0`)** — direct PoE or customer LAN. Wi‑Fi (`wlan0`) is only for tablet/AP streaming; it must never block eth0 camera DHCP.

Two separate dnsmasq configuration files:

| File                       | Interface | When active                                                |
| -------------------------- | --------- | ---------------------------------------------------------- |
| `sportassist-wifi-ap.conf` | `wlan0`   | **Only when AP is running** (written by `ldrs-wifi-ap.sh`) |
| `ldrs-camera-eth.conf`     | `eth0`    | Only when `ETH_CAMERA_DHCP=1` (see `spec-network-dhcp.md`) |

Do **not** ship `sportassist-wifi-ap.conf` in the image — a stale wlan0 snippet prevents eth0 camera DHCP from starting in client Wi‑Fi mode.

Use `bind-interfaces` and distinct subnets:

- Wi‑Fi AP: `192.168.4.0/24`
- Camera direct Ethernet: `192.168.10.0/24` (default)

---

## 8. Acceptance Criteria

1. AP broadcasts SSID `sport-assist-{serial_number}` within 60 s of boot.
2. Client with correct password connects and receives DHCP lease.
3. Web UI reachable at `http://192.168.4.1:8080/` from AP client.
4. AP remains up when Ethernet camera DHCP is toggled on/off via settings.
5. AP remains up when camera is on customer LAN (Ethernet DHCP off).
6. SSID and password traceable to `config/appliance.env` used at construction.
