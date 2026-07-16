# Live Video Delay Replay System — Build Instructions (Windows PC)

Install the Live Video Delay Replay System replay appliance on a **factory-default Raspberry Pi 5** running **Raspberry Pi OS Lite (64-bit)**.

> **GitHub / sharing:** use only `config/*.env.example` in the repo. Per-unit `config/*-*.env` files contain real secrets — keep offline and never commit.

**Repository path (this PC)**

```text
<path-to-your-clone>/live-video-delay-replay-system
```

Commands marked **PC** run in PowerShell on this Windows machine. Commands marked **Pi** run over SSH on the Pi. Follow sections **in order**. Each **Check** must pass before continuing.

**Install phases (overview)**

| Phase              | Sections    | Goal                                        |
| ------------------ | ----------- | ------------------------------------------- |
| 0 — Camera         | §0          | Web UI: password, motion/snapshot/audio off |
| A — Flash & SSH    | §1–§2       | Blank SD card → you can SSH in              |
| B — Pi base        | §3–§5       | Updated OS, fan, apt packages               |
| C — ONVIF + deploy | §4.1, §6–§8 | Copy `pi-root`, per-unit passwords          |
| D — AP + hardening | §9–§9.6     | Wi‑Fi AP + USBGuard + EEPROM                |
| E — Verify         | §10         | Phone on AP; web UI works                   |
| F — Camera         | §11         | PoE camera, replay streams                  |
| G — Production     | §14         | Pre-ship checklist; ready to deploy         |

**Gate checks (do not continue until these pass)**

| Section | Where      | Must see                                                |
| ------- | ---------- | ------------------------------------------------------- |
| §4.1    | Pi         | ONVIF pip imports + WSDL                                |
| §4.2    | Pi         | Built-in Wi‑Fi present (`brcmfmac`); `iw dev` shows `wlan*` |
| §4.3    | Pi         | No `disable-wifi-pi5` overlay; AP uses onboard radio        |
| §7      | PC then Pi | Tarball on Pi → `ldrs` files → ONVIF via `onvif_client` |
| §9      | Pi         | `hostapd` **active**; `usbguard.service` **active**     |
| §9.6    | Pi         | After reboot: `BOOT_ORDER=0xf1`                         |
| §10     | Phone + Pi | Wi‑Fi AP, services, web UI                              |
| §11     | Pi + phone | RTSP + HLS; **Direct to replay unit via PoE Injector**  |
| §14     | Bench      | Pre-ship checklist complete                             |

Full detail for built-in Wi‑Fi AP, NetworkManager, USB hardening, and camera modes: **`build-instructions-mac.md`** (canonical long form). This PC guide mirrors the same manufacturing flow.

---

## 0. Prepare the IP camera (do this first)

Before you flash the Pi SD card or start §1:

1. Power the PoE camera on your **home network** (PoE injector or switch — **not** connected to the Pi yet).
2. Find its IP address (router DHCP client list or the manufacturer’s discovery tool).
3. Open the camera **web UI** in a browser: `http://<camera-ip>` (e.g. `http://192.168.1.81`).
4. Log in as **`admin`** with the **factory** password (check the camera label / vendor manual — keep it private). The first field project used a **UNV (UniView) turret**.
5. In account / user settings, change the **admin password** to a **strong site-private** password and save it offline (password manager or construction log — **never commit it to git**).
6. Set the **main stream frame rate to 25 fps** (required for 1‑second HLS/GOP alignment).
7. Confirm main + sub stream encodings suitable for remux (4K + 1080p when available).
8. Set time zone / NTP; use an indoor day profile (disable IR / white light / night mode if the venue is always lit).
9. Confirm **ONVIF** and **RTSP** are enabled.
10. **Turn off Events → Motion Detection** (disable motion detection and related event alarms).
11. **Disable Third Stream** only — keep **main** and **sub** streams enabled (sub stream is required for Wi‑Fi replay; the Pi configures both via ONVIF at assign).
12. **Turn off Snapshot**.
13. **Turn off Audio** (disable the microphone / audio encoding).

**Check:** you can log into the camera web UI with **`admin`** and your **private** password; 25 fps; motion detection off; third stream off; snapshot off; audio off; sub stream still enabled.

When you reach **§11 Assign camera**, enter that same **`admin`** / private password once. The Pi creates a dedicated **`sportassist`** streaming user via ONVIF and stores only those assigned credentials.

Requires **OpenSSH Client** on Windows (Settings → Apps → Optional features → OpenSSH Client).

---

## 1. Hardware and software requirements

| Item     | Requirement                                                |
| -------- | ---------------------------------------------------------- |
| Board    | Raspberry Pi 5 Model B, 4 GB RAM                           |
| Storage  | 64 GB microSD minimum                                      |
| OS       | Raspberry Pi OS Lite — 64-bit (Bookworm or later)          |
| Camera   | PoE IP camera on Ethernet (preferred: UNV IPC3638SB)       |
| Wi‑Fi AP | Raspberry Pi **built-in** Wi‑Fi — verify **§4.2** |
| Network  | PoE injector or switch; optional 4K HDMI coach monitor     |
| Build PC | Windows with SSH and `scp` (OpenSSH Client)                |

After install the Pi runs an always-on Wi‑Fi AP (`sport-assist-{serial}`), RTSP ingest → dual HLS buffers (Wi‑Fi tablets), optional 4K HDMI coach display (delayed HLS + **mpv**; logo when no video), and HTTP at **`http://192.168.4.1`**.

---

## 2. Flash the SD card

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

1. **Choose device** → Raspberry Pi 5
2. **Choose OS** → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (64-bit)**
3. **Choose storage** → your microSD card
4. Click the **gear** and set:

   | Setting           | Value                                  |
   | ----------------- | -------------------------------------- |
   | Hostname          | `sport-assist`                         |
   | Username          | `sportassist`                          |
   | Password          | `your Imager password`                 |
   | Enable SSH        | On (password authentication)           |
   | Locale / timezone | Your site (e.g. `GB`, `Europe/London`) |
   | Wi‑Fi country     | Your regulatory domain (e.g. `GB`)     |

5. Write the image. Insert the SD card into the Pi 5.

**First boot**

- Connect **Ethernet** to your LAN (camera wiring comes later).
- Power on; wait ~90 seconds.

**PC** — connect (PowerShell):

```powershell
ssh sportassist@sport-assist.local
# password: your Imager password
```

If you rebuilt the SD card and SSH warns `REMOTE HOST IDENTIFICATION HAS CHANGED`:

```powershell
ssh-keygen -R sport-assist.local
ssh sportassist@sport-assist.local
```

If `.local` does not resolve, use the Pi IP from your router:

```powershell
ssh sportassist@<pi-ip-address>
ssh-keygen -R <pi-ip-address>   # if host key changed
```

Fan control is configured in **§3.1** (`/boot/firmware/config.txt`) — not in `raspi-config` on Pi 5.

---

## 3. Initial system update

**Pi**

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt autoremove -y
sudo reboot
```

SSH back in after reboot.

**Check — Pi 5, 64-bit**

```bash
uname -m          # expect aarch64
cat /proc/device-tree/model
free -h           # expect ~3.8 GiB total on 4 GB board
```

### 3.1 Pi 5 — active cooler fan

**Pi** — check current settings:

```bash
CONFIG=/boot/firmware/config.txt
grep -nE '^dtparam=cooling_fan|^dtparam=fan_temp[0-3]' "$CONFIG" || echo '(no fan dtparams — using firmware defaults)'
vcgencmd measure_temp
```

**Pi** — apply if `cooling_fan=on` or `fan_temp0=60000` is missing:

```bash
CONFIG=/boot/firmware/config.txt

sudo sed -i \
  -e '/^dtparam=cooling_fan=/d' \
  -e '/^dtparam=fan_temp0=/d' \
  -e '/^# sport-assist Pi 5 active cooler/d' \
  "$CONFIG"

sudo tee -a "$CONFIG" >/dev/null <<'EOF'

# sport-assist Pi 5 active cooler (first speed step at 60°C)
dtparam=cooling_fan=on
dtparam=fan_temp0=60000
EOF

sudo reboot
```

**Check** after reboot:

```bash
grep -E '^dtparam=cooling_fan|^dtparam=fan_temp0' /boot/firmware/config.txt
vcgencmd measure_temp
ls /proc/device-tree/cooling_fan/ 2>/dev/null && echo 'cooling_fan device tree node: OK'
```

### 3.2 Stay awake — no sleep or display blanking

**Pi**

```bash
CMDLINE=/boot/firmware/cmdline.txt
CONFIG=/boot/firmware/config.txt

grep -qE '(^| )consoleblank=0($| )' "$CMDLINE" || sudo sed -i 's/$/ consoleblank=0/' "$CMDLINE"

if grep -qE '^hdmi_blanking=' "$CONFIG"; then
  sudo sed -i 's/^hdmi_blanking=.*/hdmi_blanking=0/' "$CONFIG"
elif ! grep -qE '^# sport-assist — keep HDMI active' "$CONFIG"; then
  sudo tee -a "$CONFIG" >/dev/null <<'EOF'

# sport-assist — keep HDMI active (coach monitor)
hdmi_blanking=0
EOF
fi

sudo reboot
```

**Check** after reboot:

```bash
systemctl is-enabled ldrs-no-sleep.service 2>/dev/null || echo '(ldrs-no-sleep not installed yet — enabled in §9)'
grep -E 'consoleblank=0|hdmi_blanking=0' /boot/firmware/cmdline.txt /boot/firmware/config.txt
cat /sys/module/kernel/parameters/consoleblank   # expect 0
```

### 3.3 Pi 5 — HDMI 4K (coach monitor)

If using a 4K poolside HDMI display, ensure firmware allows 4K output. Edit boot config:

**Pi**:

```bash
sudo nano /boot/firmware/config.txt
```

Add or confirm (validate with your monitor):

```ini
hdmi_enable_4kp60=1
```

Save and exit nano (**Ctrl+O**, Enter, **Ctrl+X**), then reboot:

```bash
sudo reboot
```

SSH back in after reboot.

**Check**

**Pi**:

```bash
grep -E '^hdmi_enable_4kp60' /boot/firmware/config.txt
```

Expect **`hdmi_enable_4kp60=1`**.

Exact mode lines may need tuning per monitor — see `.cursor/spec-hdmi-output.md`.

---

## 4. Install packages

**Pi**

```bash
sudo apt install -y \
  ffmpeg \
  vlc \
  mpv \
  hostapd \
  dnsmasq \
  iw \
  jq \
  curl \
  python3 \
  python3-flask \
  python3-venv \
  python3-pip \
  python3-zeep \
  iproute2 \
  iptables \
  avahi-daemon
```

This installs the Wi‑Fi AP (`hostapd`, `dnsmasq`), video tools (`ffmpeg`, `vlc`, `mpv` for delayed HDMI), and Python stack.

### 4.1 ONVIF (required)

**PC** — copy `requirements-pip.txt` to the Pi (not inside the tarball):

```powershell
cd C:\Users\micro\Documents\Sport\VideoReplaySystem\live-video-delay-replay-system
scp requirements-pip.txt sportassist@sport-assist.local:/home/sportassist/
```

**Check — file on Pi**

```bash
ls -la /home/sportassist/requirements-pip.txt
```

**Pi** — install ONVIF packages with `sudo` (same context as `ldrs-*` helpers):

```bash
cd /home/sportassist
sudo pip3 install \
  --break-system-packages \
  --ignore-installed isodate \
  --no-binary onvif-zeep \
  -r requirements-pip.txt
```

Use `--ignore-installed isodate` (Pi OS ships a dummy apt `isodate` package). Use `--no-binary onvif-zeep` (piwheels wheel omits WSDL files).

**Pi** — fix WSDL placement (required after pip install):

```bash
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
DEST="/usr/local/lib/python${PYVER}/site-packages/wsdl"
DIST="/usr/local/lib/python${PYVER}/dist-packages/wsdl"

if [[ ! -f "${DEST}/devicemgmt.wsdl" ]]; then
  WSRC=$(find /usr/local/lib -name devicemgmt.wsdl 2>/dev/null | head -1 || true)
  if [[ -n "$WSRC" ]]; then
    sudo mkdir -p "$DEST"
    sudo cp -a "$(dirname "$WSRC")/." "$DEST/"
  else
    TMP=$(mktemp -d)
    pip3 download --no-deps --no-binary onvif-zeep 'onvif-zeep>=0.2.12' -d "$TMP"
    tar -xzf "$TMP"/onvif_zeep-*.tar.gz -C "$TMP"
    sudo mkdir -p "$DEST"
    sudo cp -a "$TMP"/onvif_zeep-*/wsdl/. "$DEST/"
    rm -rf "$TMP"
  fi
fi

if [[ -f "${DEST}/devicemgmt.wsdl" && ! -e "${DIST}/devicemgmt.wsdl" ]]; then
  sudo mkdir -p "$(dirname "$DIST")"
  sudo ln -sfn "$DEST" "$DIST"
fi
```

**Check — ONVIF pip packages** (must work with `sudo`):

```bash
sudo python3 -c "
from onvif import ONVIFCamera
from wsdiscovery import WSDiscovery
import pathlib

print('onvif import: OK')
print('WSDiscovery import: OK')

wsdl_dir = None
import onvif
roots = [pathlib.Path(onvif.__file__).resolve().parent.parent,
         pathlib.Path(onvif.__file__).resolve().parent]
seen = set()
for root in roots:
    for candidate in (root / 'wsdl', root):
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / 'devicemgmt.wsdl').is_file():
            wsdl_dir = candidate
            break
    if wsdl_dir:
        break
    for hit in root.rglob('devicemgmt.wsdl'):
        wsdl_dir = hit.parent
        break
    if wsdl_dir:
        break

if wsdl_dir:
    print('wsdl:', wsdl_dir)
else:
    print('wsdl: NOT FOUND')
    raise SystemExit(1)
"
```

**If WSDL NOT FOUND** — re-run the **fix WSDL placement** block above, then re-run the check. Diagnostic:

```bash
find /usr/local/lib -name devicemgmt.wsdl 2>/dev/null
python3 -c "import onvif; print(onvif.__file__)"
```

Re-run the **Check — ONVIF pip packages** until it passes.

### 4.2 Raspberry Pi built-in Wi‑Fi — production AP

The venue **Wi‑Fi AP** uses the **Raspberry Pi 5 built-in radio** (`brcmfmac`, typically `wlan0`). No USB Wi‑Fi adapter is required. Full steps: **`build-instructions-mac.md` §4.2**.

**Check (Pi):**

```bash
iw dev
readlink -f /sys/class/net/wlan*/device/driver 2>/dev/null
```

Expect a `wlan*` interface whose driver path contains **`brcmfmac`**.

Leave **`AP_INTERFACE` unset** in `wifi-ap.env` (§8) — `ldrs-wifi-ap.sh` auto-selects the built-in radio.

### 4.3 Ensure onboard Wi‑Fi is enabled

Do **not** add `dtoverlay=disable-wifi-pi5`. See **`build-instructions-mac.md` §4.3**.

```bash
sudo /usr/local/bin/ldrs-ensure-builtin-wifi.sh
# reboot only if the script reports that dtoverlay lines were removed
```

After any required reboot: `brcmfmac` `wlan*` present; `sudo iw dev | grep -E 'type AP|ssid'` shows your SSID when the AP is running.

**Pi** — Wi‑Fi AP prep (NetworkManager must not manage the AP interface):

```bash
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/unmanaged-wifi-ap.conf >/dev/null <<'EOF'
[device]
wifi.scan-rand-mac-address=no

[keyfile]
unmanaged-devices=interface-name:wlan0
EOF
sudo systemctl restart NetworkManager || true

sudo systemctl unmask hostapd
sudo systemctl disable hostapd dnsmasq
```

---

## 5. Create system user group and buffer directories

**Pi**

```bash
sudo groupadd -f sportassist
sudo usermod -aG sportassist sportassist

sudo mkdir -p /var/lib/sportassist/hls
sudo mkdir -p /var/lib/sportassist/hls-4k
sudo mkdir -p /run/sportassist
sudo chown -R sportassist:sportassist /var/lib/sportassist
sudo chmod 750 /var/lib/sportassist
```

---

## 6. Per-unit construction config

**PC**

```powershell
cd C:\Users\micro\Documents\Sport\VideoReplaySystem\live-video-delay-replay-system\config

Copy-Item appliance.env.example appliance-UNIT123456.env
Copy-Item web.env.example           web-UNIT123456.env
```

Edit `appliance-UNIT123456.env`:

```bash
APPLIANCE_SERIAL=UNIT123456
AP_PSK='Your-WiFi-AP-Passphrase-Min-8-Chars'
AP_COUNTRY_CODE=GB
```

Set values from `config/web.env.example` (field meanings: **`.cursor/spec-settings-page.md` §3**):

```bash
SETTINGS_USERNAME='admin'
SETTINGS_PASSWORD='Your-Web-Login-Password'
SETTINGS_VIEW_PASSWORD='Your-Settings-View-Password'
FLASK_SECRET_KEY='paste-output-below'
WEB_SESSION_TIMEOUT=28800
```

Generate `FLASK_SECRET_KEY` (requires OpenSSL on PATH, e.g. Git for Windows):

```powershell
cd C:\Users\micro\Documents\Sport\VideoReplaySystem\live-video-delay-replay-system\config
openssl rand -hex 32
```

Paste the 64-character hex string into `web-UNIT123456.env`. **Do not commit real passwords to git.**

---

## 7. Copy `pi-root` to the Pi

Run **7.1** on the PC, then **7.2–7.6** on the Pi in order.

### 7.1 Pack and copy (PC)

From repo root — **not** in the Pi SSH session:

```powershell
cd C:\Users\micro\Documents\Sport\VideoReplaySystem\live-video-delay-replay-system

tar -czf pi-root-sync.tar.gz -C pi-root .
scp pi-root-sync.tar.gz sportassist@sport-assist.local:/home/sportassist/
scp requirements-pip.txt        sportassist@sport-assist.local:/home/sportassist/
scp config/appliance-UNIT123456.env sportassist@sport-assist.local:/home/sportassist/appliance.env
scp config/web-UNIT123456.env       sportassist@sport-assist.local:/home/sportassist/web.env
```

On Git Bash or WSL you can use the helper (filename suffix must match `appliance-{SUFFIX}.env`):

```bash
./scripts/push-to-pi.sh UNIT123456
```

### 7.2 Check — tarball on the Pi

```bash
ssh sportassist@sport-assist.local
ls -la /home/sportassist/pi-root-sync.tar.gz /home/sportassist/requirements-pip.txt
```

### 7.3 Extract `pi-root` (Pi)

Skip the `pip3 install` line if you already passed the §4.1 ONVIF check.

```bash
sudo tar xzf /home/sportassist/pi-root-sync.tar.gz -C / --no-same-owner --skip-old-files
```

### 7.4 Check — `ldrs` code deployed (Pi)

```bash
test -f /home/sportassist/dev/ldrs/lib/onvif_client.py && echo "ldrs: OK" || { echo "ldrs: FAIL"; exit 1; }
```

### 7.5 Fix ownership (Pi)

Run immediately after extract (Windows tarballs are usually fine; this script is safe to re-run):

```bash
sudo /usr/local/bin/ldrs-fix-pi-root-ownership.sh
```

### 7.6 Check — ONVIF via `onvif_client` (Pi)

```bash
sudo python3 -c "
import sys
sys.path.insert(0, '/home/sportassist/dev/ldrs')
from lib.onvif_client import onvif_wsdl_dir, onvif_available
print('onvif:', onvif_available(), 'wsdl:', onvif_wsdl_dir())
"
```

Expect: `onvif: True wsdl: ...` — if not, return to §4.1.

---

## 8. Merge construction config into runtime env files

**Pi**

```bash
sudo bash -c 'source /home/sportassist/appliance.env
cat > /etc/sportassist/wifi-ap.env <<EOF
APPLIANCE_SERIAL=${APPLIANCE_SERIAL}
AP_SSID=sport-assist-${APPLIANCE_SERIAL}
AP_PSK=${AP_PSK}
AP_COUNTRY_CODE=${AP_COUNTRY_CODE}
AP_CHANNEL=6
AP_ADDRESS=192.168.4.1
AP_NETMASK=255.255.255.0
AP_DHCP_RANGE_START=192.168.4.100
AP_DHCP_RANGE_END=192.168.4.150
AP_DHCP_LEASE_TIME=24h
EOF'

sudo install -m 640 -o root -g sportassist /home/sportassist/web.env /etc/sportassist/web.env
sudo install -m 600 -o root -g root /home/sportassist/appliance.env /etc/sportassist/appliance.env
sudo rm -f /home/sportassist/appliance.env /home/sportassist/web.env /home/sportassist/pi-root-sync.tar.gz

sudo chown root:sportassist /etc/sportassist/*.env
sudo chmod 640 /etc/sportassist/camera.env \
                 /etc/sportassist/web.env \
                 /etc/sportassist/network.env \
                 /etc/sportassist/system.env \
                 /etc/sportassist/wifi-ap.env
sudo chown root:sportassist /etc/sportassist/wifi-ap.env
sudo chmod 600 /etc/sportassist/appliance.env

sudo tee /etc/sportassist/lens-presets.json >/dev/null <<'EOF'
{
  "activePresetId": "wide",
  "presets": [
    { "id": "wide", "label": "Wide pool", "zoom": 0.0, "focus": 0.5 },
    { "id": "board", "label": "Board", "zoom": 0.35, "focus": 0.5 }
  ]
}
EOF
sudo chown root:sportassist /etc/sportassist/lens-presets.json
sudo chmod 640 /etc/sportassist/lens-presets.json
```

---

## 9. Enable and start services

**Pi** — brand-new Pi (no camera yet). **Do not enable `ldrs-network` yet** — that moves `eth0` off your router and breaks SSH until the Wi‑Fi AP works.

**Before you run this:** `ldrs-usb-hardening.service` builds a USBGuard allowlist from connected USB devices (typically Pi hubs). No Wi‑Fi dongle is required.

```bash
lsusb   # optional

sudo systemctl daemon-reload

sudo systemctl enable --now ldrs-no-sleep.service
sudo systemctl enable --now ldrs-usb-hardening.service
sudo systemctl enable --now ldrs-wifi-ap.service
sudo systemctl enable --now ldrs-web.service

sudo systemctl disable --now ldrs-network.service 2>/dev/null || true
sudo systemctl disable --now ldrs-camera-discovery.service
sudo systemctl disable --now ldrs-replay-buffer.service
sudo systemctl disable --now ldrs-hdmi-delay.service ldrs-hdmi-live.service ldrs-hdmi-apply.service ldrs-hdmi-idle.service 2>/dev/null || true
```

**Check — must pass before reboot**

```bash
sleep 2
sudo systemctl is-active ldrs-wifi-ap.service hostapd ldrs-web.service ldrs-no-sleep.service usbguard.service
sudo iw dev | grep -E 'type AP|ssid'
curl -sS -o /dev/null -w "web login -> %{http_code}\n" http://127.0.0.1:8080/settings/login
sudo usbguard list-devices | head -20
```

Expect `type AP`, your SSID (e.g. `sport-assist-UNIT123456`), and `usbguard.service` **active**. If `hostapd` is **failed**, run:

```bash
sudo /usr/local/bin/ldrs-diagnose-ap.sh
sudo /usr/local/bin/ldrs-wifi-ap.sh
```

**Do not reboot** until `hostapd` is active and `iw dev` shows the AP on the built-in `wlan*`.

**Reboot the Pi**

```bash
sudo reboot
```

Wait ~90 seconds. On your phone, join **`sport-assist-{APPLIANCE_SERIAL}`** (from §6, e.g. `sport-assist-UNIT123456`). Open **`http://192.168.4.1`**.

SSH over **site Ethernet** still works until you enable `ldrs-network` in §11.

### 9.6 USB physical security (manufacturing — required before ship)

After the §9 reboot, verify USB hardening (full detail: **`build-instructions-mac.md` §9.6**):

```bash
sudo systemctl is-active usbguard.service ldrs-usb-hardening.service
sudo usbguard list-devices
rpi-eeprom-config | grep BOOT_ORDER
test -f /var/lib/sportassist/usbguard-configured && echo 'usbguard stamp: OK'
sudo /usr/local/bin/ldrs-diagnose-ap.sh
```

| Check              | Expected                             |
| ------------------ | ------------------------------------ |
| `usbguard.service` | `active`                             |
| `BOOT_ORDER`       | **`0xf1`**                           |
| Built-in Wi‑Fi AP  | `ldrs-diagnose-ap.sh` shows `brcmfmac` OK |

**Re-apply USB policy:** `sudo LDRS_FORCE_USB_HARDENING=1 /usr/local/bin/ldrs-apply-usb-hardening.sh` → reboot.

**Bench USB debug:** `sudo systemctl stop usbguard.service` (restart when done).

Do **not** ship until §9.6 passes.

---

## 10. Verify installation (before camera)

### 10.1 Wi‑Fi AP (phone)

1. **Settings → Wi‑Fi** → **`sport-assist-{APPLIANCE_SERIAL}`**
2. Enter **`AP_PSK`**
3. Confirm IP on `192.168.4.100`–`192.168.4.150`

### 10.2 Services (Pi)

```bash
sudo systemctl is-active ldrs-wifi-ap.service hostapd ldrs-web.service ldrs-no-sleep.service usbguard.service
sudo systemctl is-enabled ldrs-camera-discovery.service ldrs-replay-buffer.service ldrs-network.service
```

### 10.3 Web UI (phone)

Open **`http://192.168.4.1`**. Log in with **`SETTINGS_USERNAME`** and **`SETTINGS_PASSWORD`** from §6 (default **`admin`**). **`/settings`** may require **`SETTINGS_VIEW_PASSWORD`** if configured.

### 10.4 API (phone browser or Pi)

Unauthenticated `/api/status` and `/hls/*` return **401**. After web login (§10.3):

```bash
curl -sS -o /dev/null -w "status unauth -> %{http_code}\n" http://127.0.0.1:8080/api/status
```

Expect **`401`** before login. HLS → **404** after login is normal until §11.

---

## 11. Camera and replay setup

Only after §10 and §9.6 pass.

### 11.1 Bench wiring vs production

| Phase              | Pi `eth0`             | Settings → Camera Ethernet                                 |
| ------------------ | --------------------- | ---------------------------------------------------------- |
| Build (§2–§10)     | Home router           | Defaults — `ldrs-network` disabled                         |
| Production         | PoE injector → camera | **Direct to replay unit via PoE Injector**                 |
| Camera on home LAN | Home router           | **Customer LAN** — manual IP; **Search for camera on LAN** |

**Subnets:** Wi‑Fi AP gateway **`192.168.4.1`** (tablets). Camera Ethernet **`192.168.10.1`** (PoE subnet only).

Toggling Camera Ethernet mode **clears** saved camera IP. Direct mode has **no manual IP** — **Save Settings** → **Refresh camera** after PoE connect. Use **Clear camera** to reset credentials.

### 11.2 Enable camera and replay

1. Connect the **PoE camera** to Pi **Ethernet** (`eth0`).
2. Open **Settings** at `http://192.168.4.1/settings`.
3. Select Camera Ethernet mode (§11.1) → **Save Settings** → **Refresh camera** or **Search for camera on LAN**.
4. **Assign camera** (**`admin`** and the **private** password from §0).
5. **Pi** — enable Ethernet camera network and replay services:

   ```bash
   sudo systemctl enable --now ldrs-network.service
   sudo systemctl enable --now ldrs-camera-discovery.service
   sudo systemctl enable --now ldrs-camera-watch.timer
   sudo systemctl enable --now ldrs-replay-buffer.service
   sudo systemctl enable --now ldrs-hdmi-apply.service
   ```

   After `ldrs-network`, `eth0` is **`192.168.10.1`** — SSH via your home router stops. Use the Wi‑Fi AP (`192.168.4.1`) or a direct cable to `192.168.10.1`.

6. **Check RTSP**

   ```bash
   set -a; source /etc/sportassist/camera.env; set +a
   ffprobe -hide_banner -rtsp_transport tcp \
     "rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${CAMERA_IP}:554${CAMERA_RTSP_PATH}" 2>&1 | head -20
   ```

7. **Check HLS**

   ```bash
   curl -sS http://127.0.0.1:8080/hls/live.m3u8 | head
   ls -la /var/lib/sportassist/hls/
   ls -la /var/lib/sportassist/hls-4k/
   ```

8. **Check HDMI** — connect coach monitor if used

   During the first **`LIVE_DELAY_SECONDS`** of warm-up, HDMI should show the idle splash logo (`ldrs-hdmi-idle.service`). Then delayed video replaces it.

   ```bash
   ls -la /usr/share/sportassist/SportAssistLogo.png
   sudo systemctl is-active ldrs-replay-buffer.service ldrs-hdmi-apply.service ldrs-hdmi-idle.service
   sudo /usr/local/bin/ldrs-diagnose-hdmi-delay.sh
   ```

   Expect `mpv` on `http://127.0.0.1:8080/hls-4k/delayed_hdmi.m3u8`, and `delayedHdmiReady: true` in `curl -sS http://127.0.0.1:8080/api/status | jq .delayedHdmiReady` after warm-up.

---

## 12. Updating an installed Pi

**PC**

```powershell
cd C:\Users\micro\Documents\Sport\VideoReplaySystem\live-video-delay-replay-system
./scripts/push-to-pi.sh UNIT123456
```

Or manually:

```powershell
tar -czf pi-root-sync.tar.gz -C pi-root .
scp pi-root-sync.tar.gz sportassist@sport-assist.local:/home/sportassist/
scp requirements-pip.txt        sportassist@sport-assist.local:/home/sportassist/
```

**Pi** (SSH via AP `192.168.4.1` or router if `ldrs-network` not enabled)

```bash
ls -la /home/sportassist/pi-root-sync.tar.gz

sudo pip3 install \
  --break-system-packages \
  --ignore-installed isodate \
  --no-binary onvif-zeep \
  -r /home/sportassist/requirements-pip.txt

sudo systemctl stop ldrs-replay-buffer.service ldrs-hdmi-delay.service ldrs-hdmi-live.service ldrs-hdmi-idle.service 2>/dev/null || true
sudo systemctl stop ldrs-web.service ldrs-wifi-ap.service

sudo tar xzf /home/sportassist/pi-root-sync.tar.gz -C / --no-same-owner --skip-old-files
sudo /usr/local/bin/ldrs-fix-pi-root-ownership.sh

sudo systemctl daemon-reload
sudo systemctl restart ldrs-wifi-ap.service
sudo systemctl enable --now ldrs-web.service
# If USB hardening scripts changed:
# sudo LDRS_FORCE_USB_HARDENING=1 /usr/local/bin/ldrs-apply-usb-hardening.sh
# Ensure onboard Wi‑Fi is not disabled (upgrades from older images):
# sudo /usr/local/bin/ldrs-ensure-builtin-wifi.sh
# Only if camera was commissioned:
# sudo systemctl restart ldrs-network.service
# sudo systemctl restart ldrs-replay-buffer.service
# sudo systemctl restart ldrs-hdmi-apply.service

ls -la /usr/share/sportassist/SportAssistLogo.png
sudo iw dev | grep -E 'type AP|ssid'
sudo rm -f /home/sportassist/pi-root-sync.tar.gz
```

`--skip-old-files` preserves existing `/etc/sportassist/*.env`. If `/usr/local/bin/ldrs-*.sh` did not change after extract, re-run with **`--overwrite`** or copy changed scripts manually, then `sudo systemctl daemon-reload`.

Confirm AP still shows in `iw` before you disconnect.

---

## 13. Troubleshooting

### Locked out (no AP, no SSH)

| Situation                     | How to get in                                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------------------------------- |
| During build (before §11)     | Pi on **router Ethernet** → `ssh sportassist@sport-assist.local`                                          |
| After §11 (`ldrs-network` on) | **HDMI + keyboard**, or direct cable PC↔Pi with PC IP `192.168.10.2`, then `ssh sportassist@192.168.10.1` |
| AP down but §11 not run yet   | Router Ethernet SSH (above)                                                                               |

On the Pi console:

```bash
sudo /usr/local/bin/ldrs-diagnose-ap.sh
sudo systemctl restart ldrs-wifi-ap.service
```

### Common issues

| Symptom                              | Fix                                                                                                   |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `pi-root-sync.tar.gz: No such file`  | Run §7.1 on the PC — not on the Pi                                                                    |
| `hostapd` failed / no SSID           | NetworkManager conflict — redeploy `ldrs-wifi-ap.sh`, run `ldrs-diagnose-ap.sh`                       |
| Rebooted before AP worked            | eth0 may be `192.168.10.1` — use HDMI or direct cable to `192.168.10.1`                               |
| Settings `onvif_not_installed`       | §4.1 pip install + check                                                                              |
| WSDL NOT FOUND                       | §4.1 recovery (reinstall + symlink)                                                                   |
| AP not visible                       | `sudo journalctl -u hostapd -n 50`; `rfkill list`; Wi‑Fi country GB                                   |
| `curl: Could not connect` to `:8080` | Wait a few seconds; `sudo journalctl -u ldrs-web -n 30`                                               |
| No HLS segments                      | Camera assigned? `sudo systemctl status ldrs-replay-buffer`                                           |
| Scripts not updating after §12       | `tar xzf … --overwrite` instead of `--skip-old-files`                                                 |
| HDMI blank (no logo, no video)       | `ls /usr/share/sportassist/SportAssistLogo.png`; `systemctl status ldrs-hdmi-idle`                    |
| HDMI delay wrong / ring not ready    | `sudo /usr/local/bin/ldrs-diagnose-hdmi-delay.sh`                                                     |
| USB keyboard blocked                 | `sudo systemctl stop usbguard.service` (bench only); §9.6                                             |
| Camera not found (direct mode)       | PoE on `eth0`? **Save Settings** → **Refresh camera**; `grep ETH_CAMERA /etc/sportassist/network.env` |
| Stale camera IP                      | **Clear camera** in Settings or toggle Camera Ethernet mode                                           |

---

## 14. Manufacturing and production

Build **one unit per serial**. Each unit needs unique **`APPLIANCE_SERIAL`**, **`AP_PSK`**, **`SETTINGS_USERNAME`**, **`SETTINGS_PASSWORD`**, and optional **`SETTINGS_VIEW_PASSWORD`** (§6). Record on the build sheet — **do not commit real passwords to git**.

### 14.1 Per-unit flow

| Step                   | Section                                        |
| ---------------------- | ---------------------------------------------- |
| Prepare camera         | §0                                             |
| Flash + base OS        | §1–§5 (router Ethernet; built-in Wi‑Fi available) |
| Deploy per-unit config | §6–§8                                          |
| AP + USB hardening     | §9–§9.6 (`BOOT_ORDER=0xf1` after reboot)       |
| Verify base build      | §10                                            |
| Commission camera      | §11 (direct PoE mode)                          |
| Pre-ship gate          | §14.2                                          |

### 14.2 Pre-ship checklist

- [ ] Serial, SSID, `AP_PSK`, `SETTINGS_USERNAME`, `SETTINGS_PASSWORD`, optional `SETTINGS_VIEW_PASSWORD` recorded
- [ ] §10 — AP + settings login on phone
- [ ] §9.6 — `usbguard` active; `BOOT_ORDER=0xf1`
- [ ] §4.2–§4.3 — built-in Wi‑Fi AP (`brcmfmac`; no `disable-wifi-pi5`)
- [ ] §11 — camera assigned; RTSP + HLS OK; direct PoE mode
- [ ] HDMI OK if coach monitor fitted
- [ ] `sudo /usr/local/bin/ldrs-diagnose-ap.sh` clean
- [ ] `ldrs-network`, `ldrs-replay-buffer`, `ldrs-camera-discovery` enabled

### 14.3 Field service

| Task                 | Action                                                                                |
| -------------------- | ------------------------------------------------------------------------------------- |
| Software update      | §12                                                                                   |
| Re-apply USB policy  | `sudo LDRS_FORCE_USB_HARDENING=1 /usr/local/bin/ldrs-apply-usb-hardening.sh` → reboot |
| Restore onboard Wi‑Fi | `sudo /usr/local/bin/ldrs-ensure-builtin-wifi.sh` → reboot if needed                 |
| USB debug            | `sudo systemctl stop usbguard.service`                                                |
| Full reset           | Reflash SD (§2); repeat §6–§14                                                        |

Full manufacturing detail: **`build-instructions-mac.md` §14**.

Canonical behaviour: `.cursor/architecture-and-technical-spec.md`
