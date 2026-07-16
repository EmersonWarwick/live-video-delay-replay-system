# Spec: Camera Discovery and Configuration

Normative specification for finding the IP camera in **both Ethernet modes**, saving credentials on the Pi, and configuring streams via **ONVIF**.

Related: `.cursor/spec-settings-page.md`, `.cursor/spec-network-dhcp.md`, `.cursor/spec-api-endpoints.md`, `.cursor/spec-camera-stream-profiles.md`, `.cursor/spec-onvif-lens.md`.

---

## 1. Two Ethernet modes (summary)

| Pi DHCP on `eth0`       | Settings label                | Camera connection                        | How the Pi finds the camera                                                                         |
| ----------------------- | ----------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **`ETH_CAMERA_DHCP=1`** | **Direct to Raspberry Pi**    | Camera → PoE injector/switch → Pi `eth0` | Pi is DHCP server; reads **dnsmasq lease** for the one camera; **auto-fills name + IP** on Settings |
| **`ETH_CAMERA_DHCP=0`** | **Customer Ethernet network** | Camera + Pi on site LAN                  | Pi **searches** eth0 network (ONVIF + RTSP); user **selects** camera on Settings; name + IP saved   |

In **both** modes, after credentials are saved:

- Pi **auto-configures** RTSP streams via ONVIF (fallback ladder).
- Settings controls **camera** (streams, credentials) and **lens** (zoom, focus, presets) via ONVIF as far as the camera supports.

---

## 2. Direct mode (`ETH_CAMERA_DHCP=1`) — Pi DHCP server ON

### 2.1 Expected wiring

```text
[Camera] ── PoE ── [Injector or PoE switch] ── [Pi eth0]
```

Exactly **one** camera is expected on this link (assigned hostname **`SportAssistCam`** per §4).

### 2.2 Boot / discovery behaviour

1. `ldrs-network.sh` assigns Pi `PI_STATIC_IP` (default `192.168.10.1`) and starts dnsmasq on `eth0`.
2. Camera receives DHCP lease (`192.168.10.100`–`150`) with hostname `SportAssist-{serial}`.
3. `ldrs-camera-discovery.service` runs `apply_direct_discovery.py`:
   - Reads `/var/lib/misc/dnsmasq.leases`
   - Writes `CAMERA_HOSTNAME` and `CAMERA_IP` to `camera.env` (credentials still empty until operator saves)
   - Writes `/run/sportassist/camera.ip`
4. **Settings page** shows hostname and IP on **GET** (read from `camera.env`).

### 2.3 Settings UI (direct)

| Control              | Behaviour                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------- |
| Hostname / IP fields | Pre-filled from discovery; operator may **Refresh camera**                                              |
| **Refresh camera**   | `POST /api/camera/discover` — re-read DHCP leases                                                       |
| Username / password  | Operator enters **current** factory login; **Assign camera** provisions `sportassist` + random password |
| Lens section         | ONVIF move / AF / presets (see `spec-onvif-lens.md`)                                                    |

Operator does **not** need to search manually in normal direct installs.

---

## 3. Customer LAN mode (`ETH_CAMERA_DHCP=0`) — Pi DHCP server OFF

### 3.1 Expected wiring

```text
[Camera] ── site PoE switch ── [Customer LAN] ◄── [Pi eth0 DHCP client]
[Phone/tablet] ── Pi Wi‑Fi AP ──► Settings in browser or app
```

### 3.2 Search behaviour (`POST /api/camera/discover`)

Pi searches on **Ethernet only** (not Android):

1. **ONVIF WS-Discovery** on `eth0` — all ONVIF devices (preferred: `SportAssist-*` / `sport-assist-*` naming).
2. **DNS / getent** for `SportAssist-*` hostnames.
3. **RTSP port scan** (`tcp/554`) on the Pi `eth0` /24 subnet — lists hosts with an RTSP service (no credential spray).

**Timeout**: up to 30 s; partial results returned as found.

### 3.3 Settings UI (customer LAN)

| Control               | Behaviour                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------- |
| **Search for camera** | Runs discovery; shows **list** (hostname + IP)                                              |
| **Select**            | Radio button per camera; fills **IP** field only (hostname assigned on Assign)              |
| Username / password   | **Current** camera login (plain text on Settings); required before assign                   |
| **Assign camera**     | `POST /api/camera/assign` → ONVIF user provision + auto hostname + configure + `camera.env` |
| Lens section          | Same ONVIF controls as direct mode                                                          |

---

## 4. Hostname on assign

On **Assign camera**, the Pi sets hostname **`SportAssistCam`** (fixed, no suffix). The hostname field on Settings is **read-only**. The Pi also reads and stores the camera’s **ONVIF device identifier** (`CAMERA_DEVICE_ID`, e.g. serial number) and **reported name** (`CAMERA_REPORTED_NAME`, e.g. model).

Discovery may show the camera’s ONVIF model name or DHCP lease name for selection — that label is **not** used as the assigned hostname.

| Pattern            | When used                                 |
| ------------------ | ----------------------------------------- |
| `SportAssistCam`   | **Assigned** hostname (fixed)             |
| `SportAssist-*`    | DHCP / discovery display only             |
| Discovery fallback | `onvif-192-168-1-42`, `rtsp-192-168-1-42` |

---

## 5. Camera credentials on assign

User provisioning is **standard ONVIF Device Management** (`CreateUsers` / `SetUser` with `UserLevel=Administrator`) in `lib/camera_assign.provision_assigned_user`. It is **not** UniView-proprietary; the first validated camera was a UNV turret. Cameras that block remote user create/update must have an equivalent streaming user created in the vendor Web UI first.

| Step                | Behaviour                                                                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Operator prepares   | Camera **super-user / admin** password set privately in the vendor Web UI — **never** published in git, issues, or docs                                      |
| Operator enters     | **Current** privileged ONVIF username/password once on Settings (**plain text** on page, not masked) — used only for Assign                                  |
| Pi ONVIF            | `CreateUsers` or `SetUser` → username **`sportassist`**, password **random** (12 alphanumeric)                                                               |
| Pi stores           | `CAMERA_USERNAME`, `CAMERA_PASSWORD`, `CAMERA_ASSIGNED=1` in `camera.env`                                                                                    |
| Settings (assigned) | Read-only hostname, IP, `sportassist`, and **assigned password** visible on page                                                                             |
| `GET /api/camera`   | Never includes password (mobile / API clients)                                                                                                               |

---

## 6. Persistence — `/etc/sportassist/camera.env`

(See existing keys in prior revisions — hostname, IP, credentials, `INGEST_*`, sub-stream fields.)

| Key                                   | Direct mode                                         | Customer LAN                   |
| ------------------------------------- | --------------------------------------------------- | ------------------------------ |
| `CAMERA_HOSTNAME`                     | **`SportAssistCam`** on assign                      | **`SportAssistCam`** on assign |
| `CAMERA_DEVICE_ID`                    | ONVIF serial / model id — used to relocate camera   | Same                           |
| `CAMERA_REPORTED_NAME`                | Human-readable model from camera                    | Same                           |
| `CAMERA_IP`                           | Auto from DHCP lease / discovery                    | From user selection            |
| `CAMERA_USERNAME` / `CAMERA_PASSWORD` | **`sportassist`** + generated password after assign | Same                           |
| `CAMERA_ASSIGNED`                     | `1` after successful assign                         | `1` after successful assign    |
| `INGEST_*`                            | After ONVIF configure                               | After ONVIF configure          |

Password **never** returned in `GET /api/camera`. Settings HTML page shows assigned password when `CAMERA_ASSIGNED=1`.

---

## 7. Helper scripts

| Script                             | Purpose                                                                             |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| `ldrs-discover-cameras.sh`         | JSON camera list — mode-aware (DHCP leases vs LAN search)                           |
| `apply_direct_discovery.py`        | Direct mode boot: lease → `camera.env`                                              |
| `ldrs-camera-discovery.sh`         | Boot: direct apply + IP resolve by device id                                        |
| `ldrs-resolve-camera.sh`           | Verify saved IP or search network by `CAMERA_DEVICE_ID`; restart buffer on relocate |
| `ldrs-camera-watch.timer`          | Every 30 s — auto-relocate when stream lost / IP changed                            |
| `ldrs-assign-camera.sh`            | **Assign camera** — ONVIF user provision + hostname + device id + configure         |
| `ldrs-set-camera-config.sh`        | Legacy save credentials + ONVIF configure (superseded by assign for commissioning)  |
| `ldrs-configure-camera-streams.sh` | ONVIF ladder + ffprobe                                                              |
| `ldrs-onvif-lens.sh`               | Lens control from Settings                                                          |

---

## 8. ONVIF on Settings (both modes)

After the camera is reachable and credentials are saved:

| Settings area                 | ONVIF use                                |
| ----------------------------- | ---------------------------------------- |
| Assign / Re-configure streams | Media service — encoder config, profiles |
| Lens zoom / focus / stop / AF | PTZ + Imaging services                   |
| Presets                       | JSON on Pi + ONVIF where supported       |

---

## 10. IP relocation (assigned camera)

When `CAMERA_ASSIGNED=1` and streams are configured:

1. **Boot**: `ldrs-camera-discovery.service` runs `ldrs-resolve-camera.sh` before replay buffer starts.
2. **Runtime**: `ldrs-camera-watch.timer` runs `ldrs-resolve-camera.sh` every **30 s**.
3. If RTSP at `CAMERA_IP` fails, Pi searches the network (ONVIF WS-Discovery + DHCP / RTSP scan per Ethernet mode).
4. Each candidate is checked with stored `sportassist` credentials; match on **`CAMERA_DEVICE_ID`** (ONVIF serial / model).
5. On match: update `CAMERA_IP` in `camera.env`, write `/run/sportassist/camera.ip`, **restart** `ldrs-replay-buffer.service` and `ldrs-hdmi-delay.service`.

---

## 11. Acceptance criteria

1. **Direct**: camera on PoE Ethernet receives Pi DHCP lease; Settings shows **IP** without manual search.
2. **Direct**: operator can **Assign camera** with factory credentials; Pi provisions `sportassist` user and ONVIF-configures streams.
3. **Customer LAN**: search returns ONVIF and/or RTSP cameras on eth0 subnet; operator can **select** one.
4. **Customer LAN**: assigned hostname + IP persist; credentials in `camera.env`.
5. Both modes: assigned password visible on Settings page; lens controls invoke ONVIF helpers.
6. Android/iOS trigger search via Pi API only — no LAN scan on device.
7. **IP change**: assigned camera found at new address within one watchdog cycle (~30 s); streaming resumes without manual Settings intervention.
