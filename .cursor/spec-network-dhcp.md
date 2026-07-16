# Spec: Network, Ethernet DHCP, and Camera Discovery

Normative specification for Ethernet connectivity between the Raspberry Pi 5 and the IP camera.

Related: `.cursor/architecture-and-technical-spec.md`, `.cursor/spec-wifi-ap.md`, `.cursor/NetworkCameraSpec.md`.

> **Wi‑Fi AP** (always on, client access) is specified separately in **`spec-wifi-ap.md`**. This document covers **Ethernet** and **camera DHCP** only.

---

## 1. Purpose

Define how the Pi:

- Optionally hosts an **Ethernet DHCP server** on `eth0` when the camera is plugged **directly** into the Pi.
- Operates on a **customer Ethernet LAN** when the camera is on the site network (no Pi DHCP on `eth0`).
- **Discovers** the camera automatically in either case.

Manual static IP for the camera is a **commissioning fallback only**.

---

## 2. Ethernet Camera Modes

Configured in `/etc/sportassist/network.env`:

| Key                    | Values                | Meaning                             |
| ---------------------- | --------------------- | ----------------------------------- |
| `ETH_CAMERA_DHCP`      | `1` \| `0`            | Pi DHCP server on `eth0` for camera |
| `PI_INTERFACE`         | `eth0`                | Camera Ethernet interface           |
| `PI_STATIC_IP`         | e.g. `192.168.10.1`   | Pi address when `ETH_CAMERA_DHCP=1` |
| `PI_NETMASK`           | `255.255.255.0`       |                                     |
| `ETH_DHCP_RANGE_START` | e.g. `192.168.10.100` | Camera lease range                  |
| `ETH_DHCP_RANGE_END`   | e.g. `192.168.10.150` |                                     |
| `ETH_DHCP_LEASE_TIME`  | e.g. `24h`            |                                     |

**Settings page labels** (user-facing):

| UI label                      | `ETH_CAMERA_DHCP` | Use when                                              |
| ----------------------------- | ----------------- | ----------------------------------------------------- |
| **Direct to Raspberry Pi**    | `1`               | Camera Ethernet cable to Pi (via PoE injector/switch) |
| **Customer Ethernet network** | `0`               | Camera and Pi on same site LAN                        |

Toggled from `/settings` via `ldrs-set-eth-camera-dhcp.sh` — see `spec-settings-page.md`.

Legacy alias: documentation may refer to `direct` / `lan` modes; they map to `ETH_CAMERA_DHCP=1` / `0`.

### 2.1 Direct to Pi (`ETH_CAMERA_DHCP=1`)

```text
[Camera] ── PoE ── [Injector/switch] ── [Pi eth0]
```

**Pi behaviour** (`ldrs-network.sh`):

1. Set `eth0` to `PI_STATIC_IP/24`.
2. Start dnsmasq with `/etc/dnsmasq.d/ldrs-camera-eth.conf` on `eth0` only.
3. Do not run a DHCP **client** on `eth0` for the camera subnet.

**Camera**: receives DHCP lease from Pi; hostname `SportAssist-{serial_number}`.

### 2.2 Customer LAN (`ETH_CAMERA_DHCP=0`)

```text
[Camera] ── PoE switch ── [Site LAN] ◄── [Pi eth0]
[Phone/Tablet] ── Wi‑Fi AP ──► [Pi :8080/settings]  (camera search UI)
```

**Pi behaviour**:

1. Use site Ethernet configuration on `eth0` (DHCP client from customer router).
2. **Stop** dnsmasq camera DHCP on `eth0`.
3. **Discover** camera via settings **Search** or boot-time discovery — see `.cursor/spec-camera-discovery.md`.
4. Store hostname, username, password in `/etc/sportassist/camera.env`.

**Operator workflow**: Connect tablet to Pi AP → open Android app **Settings** → **Search for camera** on customer network → enter credentials → save on Pi.

**Wi‑Fi AP on `wlan0` is unaffected** — see `spec-wifi-ap.md`.

---

## 3. Ethernet DHCP Server (Direct Mode Only)

**Software**: `dnsmasq` (separate instance/config from Wi‑Fi AP)

**Config**: `/etc/dnsmasq.d/ldrs-camera-eth.conf`

```text
interface=eth0
bind-interfaces
dhcp-range=192.168.10.100,192.168.10.150,255.255.255.0,24h
domain-needed
bogus-priv
```

**Rules**

- Active **only** when `ETH_CAMERA_DHCP=1`.
- Subnet `192.168.10.0/24` must not overlap Wi‑Fi AP subnet `192.168.4.0/24`.
- Pi must not lease itself an address from the camera pool.

---

## 4. Helper: `ldrs-set-eth-camera-dhcp.sh`

Called from settings page (sudo, whitelisted).

```bash
ldrs-set-eth-camera-dhcp.sh enable   # ETH_CAMERA_DHCP=1
ldrs-set-eth-camera-dhcp.sh disable  # ETH_CAMERA_DHCP=0
```

Must:

1. Validate argument (`enable` | `disable`).
2. Backup and update `ETH_CAMERA_DHCP=` in `/etc/sportassist/network.env`.
3. Run `systemctl restart ldrs-network.service`.
4. Run `systemctl restart ldrs-camera-discovery.service`.
5. Run `systemctl restart ldrs-replay-buffer.service` (RTSP target may change).
6. Exit non-zero on failure.

**Reboot**: not required if services restart cleanly; settings page shows warning that video may drop for ~30 s during switch.

---

## 5. Camera Discovery

**Service**: `ldrs-camera-discovery.service` (after `ldrs-network.service`)

**Output**: `/run/sportassist/camera.ip` (runtime; may mirror `CAMERA_IP` in `camera.env`)

### 5.1 Direct mode (`ETH_CAMERA_DHCP=1`)

1. Camera plugs into Pi Ethernet via PoE injector/switch.
2. Pi dnsmasq leases an address; hostname `SportAssist-{serial}`.
3. `ldrs-camera-discovery.service` writes **`CAMERA_HOSTNAME`** and **`CAMERA_IP`** into `camera.env`.
4. Settings page displays name and IP; operator adds credentials and saves.
5. Optional **Refresh camera** re-runs lease discovery.

### 5.2 Customer LAN mode (`ETH_CAMERA_DHCP=0`)

1. If `camera.env` complete → resolve by **hostname** on each boot.
2. If not configured → operator uses Settings **Search for camera**.
3. User-initiated search: ONVIF WS-Discovery, DNS, **RTSP port scan** on eth0 subnet — see `spec-camera-discovery.md`.
4. Operator **selects** one camera from the list, enters credentials, saves.

**Mobile app** triggers search via Pi HTTP API; **does not** scan the LAN itself.

### 5.3 Discovery order (customer LAN search)

1. ONVIF WS-Discovery on `eth0` (all devices; prefer Sport Assist names).
2. DNS / `getent` for `SportAssist-*`.
3. RTSP `tcp/554` scan on Pi `eth0` /24 (no blind credential attempts).

### 5.2 Mode comparison

| Aspect           | Direct (`ETH_CAMERA_DHCP=1`) | Customer LAN (`ETH_CAMERA_DHCP=0`) |
| ---------------- | ---------------------------- | ---------------------------------- |
| eth0 DHCP server | Pi (dnsmasq)                 | Off                                |
| Typical subnet   | `192.168.10.0/24`            | Site-defined                       |
| Discovery        | Lease table + hostname       | DNS/mDNS/ONVIF on LAN              |
| Wi‑Fi AP         | Always on (`wlan0`)          | Always on (`wlan0`)                |

---

## 6. Service: `ldrs-network.sh`

Invoked by `ldrs-network.service` (oneshot, `RemainAfterExit=yes`).

**Always** (both modes):

- Ensure `PI_INTERFACE` link is up.

**When `ETH_CAMERA_DHCP=1`**:

- Configure static IP on `eth0`.
- Enable dnsmasq camera config; disable conflicting eth0 DHCP client.

**When `ETH_CAMERA_DHCP=0`**:

- Stop dnsmasq camera scope on `eth0`.
- Apply site eth0 profile from build/OS config.

Does **not** manage Wi‑Fi AP — that is `ldrs-wifi-ap.sh`.

---

## 7. Boot Order

```text
ldrs-wifi-ap.service          # always — wlan0 AP + client DHCP
        ↓
ldrs-network.service          # eth0 — camera DHCP on or off
        ↓
ldrs-camera-discovery.service
        ↓
ldrs-replay-buffer.service
```

---

## 8. Security

- Camera credentials in `camera.env` (mode `640`).
- Discovery logs must not print RTSP passwords.
- Ethernet DHCP scope is for the **camera link only**, not general site clients.

---

## 9. Acceptance Criteria

1. Wi‑Fi AP is up regardless of `ETH_CAMERA_DHCP` value.
2. With **Direct**, camera receives DHCP lease within 60 s of link up.
3. With **Customer LAN**, Pi does not offer DHCP on `eth0`; camera is discoverable.
4. Settings page toggle persists `ETH_CAMERA_DHCP` across reboot.
5. `/run/sportassist/camera.ip` is valid before replay buffer ingest starts.
6. Toggling Ethernet mode restarts network/discovery/stream without full system failure.
