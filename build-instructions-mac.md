# Live Video Delay Replay System — Build Instructions (Mac)

Step-by-step install on a **factory-fresh Raspberry Pi 5** with **Raspberry Pi OS Lite (64-bit)**.

> **GitHub / sharing:** use only `config/*.env.example` in the repo. Per-unit `config/appliance-*.env` and `config/web-*.env` contain real secrets — keep offline and never commit.

**Repository path**

```text
<path-to-your-clone>/live-video-delay-replay-system
```

---

## 0. Prepare the IP camera (do this first)

The first field project used a **UNV (UniView) CCTV turret**. Other ONVIF cameras follow the same idea: use the **vendor Web UI** before the Pi Assign step.

Before you flash the Pi SD card or start §1:

1. Power the PoE camera on your **home network** (PoE injector or switch — **not** connected to the Pi yet).
2. Find its IP address (router DHCP client list or the manufacturer’s discovery tool).
3. Open the camera **web UI** in a browser: `http://<camera-ip>` (e.g. `http://192.168.1.81`).
4. Log in as **`admin`** with the **factory** password (check the camera label / vendor manual — keep it private).
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

---

## How to use this guide

| Label     | Where you run commands                                       |
| --------- | ------------------------------------------------------------ |
| **Mac**   | Terminal on your Mac                                         |
| **Pi**    | SSH session to the Pi (`ssh sportassist@sport-assist.local`) |
| **Phone** | iPhone/Android on the Pi Wi‑Fi AP (later steps)              |

**Rules**

1. Follow sections **in order** — do not skip ahead.
2. Every **Check** box must pass before you continue.
3. After every **`sudo reboot`**, wait **~90 seconds**, then SSH back in before the next section.
4. Keep the Pi on **Ethernet to your home router** until **§11** (camera). That keeps SSH working while you build.
5. **Do not enable `ldrs-network` until §11** — it moves `eth0` off your router and you lose easy SSH.

**Install phases (overview)**

| Phase           | Sections       | Goal                                                                         |
| --------------- | -------------- | ---------------------------------------------------------------------------- |
| 0 — Camera      | §0             | Web UI: password, motion/snapshot/audio off, third stream off, sub stream on |
| A — Flash & SSH | §1–§2          | Blank SD card → you can SSH in                                               |
| B — Pi base     | §3–§5          | Updated OS, fan, stay-awake, apt packages                                    |
| C — ONVIF       | §4.1           | Python camera libraries on Pi                                                |
| D — Unit config | §6             | Wi‑Fi password, settings password (on Mac)                                   |
| E — Deploy code | §7–§8          | Copy `pi-root`, merge your passwords                                         |
| F — AP + web    | §9–§10         | Wi‑Fi AP works, phone can open settings                                      |
| G — Camera      | §11            | PoE camera, replay streams                                                   |
| H — Production  | §9.6, §11, §14 | USB hardening verified, camera commissioned, ready to ship                   |

**Gate checks (do not continue until these pass)**

| Section | Where      | Must see                                                                   |
| ------- | ---------- | -------------------------------------------------------------------------- |
| §2      | Mac        | SSH login works                                                            |
| §4.1    | Pi         | `onvif import: OK` and `wsdl: ...`                                         |
| §7      | Mac → Pi   | `ldrs: OK` and `onvif: True`                                               |
| §4.2    | Pi         | Built-in Wi‑Fi present (`brcmfmac`); `iw dev` shows `wlan*`                |
| §4.3    | Pi         | No `disable-wifi-pi5` overlay; AP uses onboard radio                       |
| §8      | Pi         | `wifi-ap.env` has your serial and PSK                                      |
| §9      | Pi         | `hostapd` **active**, `iw dev` shows **`type AP`** on USB `wlan*`          |
| §9.6    | Pi         | `usbguard.service` **active**; after reboot `BOOT_ORDER=0xf1`              |
| §10     | Phone      | Join Wi‑Fi AP, `http://192.168.4.1` loads                                  |
| §11     | Pi + phone | RTSP + HLS live; camera in **Direct to replay unit via PoE Injector** mode |
| §14     | Bench      | Pre-ship checklist complete; unit identity recorded                        |

---

## Before you start — checklist

Gather on the bench:

- [ ] Raspberry Pi 5 (4 GB) + official **5V 5A** USB-C power supply
- [ ] microSD card (64 GB+), card reader for your Mac
- [ ] Ethernet cable: Pi ↔ **home router** (not camera yet)
- [ ] [Raspberry Pi Imager](https://www.raspberrypi.com/software/) installed on Mac
- [ ] Phone for Wi‑Fi testing (§10)
- [ ] Raspberry Pi 5 with built-in Wi‑Fi (venue AP uses onboard radio — §4.2–§4.3)
- [ ] Optional: HDMI monitor + USB keyboard (recovery if networking fails)
- [ ] IP camera prepared via web UI (§0): private admin password; 25 fps; motion/snapshot/audio off; sub stream on

**Write down your unit values** (edit in §6; example for this repo copy):

| Setting                  | Example (this unit)                    | Used for                                   |
| ------------------------ | -------------------------------------- | ------------------------------------------ |
| `APPLIANCE_SERIAL`       | `UNIT123456`                           | Wi‑Fi name: **`sport-assist-UNIT123456`**  |
| `AP_PSK`                 | `ChangeMe-AP-Passphrase`               | Wi‑Fi password (min 8 chars)               |
| `SETTINGS_USERNAME`      | `admin` (default)                      | Web login — see `spec-settings-page.md` §3 |
| `SETTINGS_PASSWORD`      | _(you choose)_                         | Web login                                  |
| `SETTINGS_VIEW_PASSWORD` | _(optional)_                           | Settings-view unlock                       |
| Pi SSH user / password   | `sportassist` / `your Imager password` | Set in Imager (§2)                         |

---

## 1. Hardware and software requirements

| Item      | Requirement                                                  |
| --------- | ------------------------------------------------------------ |
| Board     | Raspberry Pi 5 Model B, 4 GB RAM                             |
| Storage   | 64 GB microSD minimum                                        |
| OS        | Raspberry Pi OS Lite — 64-bit (Bookworm or later)            |
| Camera    | PoE IP camera on Ethernet (§11 only — not needed for §2–§10) |
| Build Mac | Terminal with `ssh` and `scp` (built in)                     |

When finished, the Pi will run:

- Always-on Wi‑Fi AP: **`sport-assist-{serial}`** (e.g. `sport-assist-UNIT123456`)
- Web UI at **`http://192.168.4.1`** (settings, status, HLS when camera is live)
- Optional 4K HDMI coach monitor (§11) — idle splash logo when no video; delayed replay via 4K HLS + **mpv**

---

## 2. Flash the SD card

### 2.1 Write the image (Mac — Raspberry Pi Imager)

1. Open **Raspberry Pi Imager**.
2. **Choose device** → **Raspberry Pi 5**.
3. **Choose OS** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (64-bit)**.
4. **Choose storage** → your microSD card.
5. Click the **gear** icon (customise). Set **exactly**:

   | Setting           | Value                                  |
   | ----------------- | -------------------------------------- |
   | Hostname          | `sport-assist`                         |
   | Username          | `sportassist`                          |
   | Password          | `your Imager password`                 |
   | Enable SSH        | **On** — allow password authentication |
   | Locale / timezone | e.g. `GB`, `Europe/London`             |
   | Wi‑Fi country     | e.g. `GB`                              |

6. Click **Save**, then **Write**. Confirm erase. Wait until finished.
7. Eject the card, insert into Pi 5.

### 2.2 First boot wiring

- Plug **Ethernet** from Pi → **home router** (camera unplugged for now).
- Connect **power**. Wait **at least 90 seconds** (first boot is slow).

### 2.3 First SSH login (Mac)

Open **Terminal** on your Mac:

```bash
ssh sportassist@sport-assist.local
```

When prompted for password, type: **`your Imager password`** (nothing appears as you type — normal).

**Check — SSH works**

You should see a prompt like `sportassist@sport-assist:~ $`.

If SSH says **`REMOTE HOST IDENTIFICATION HAS CHANGED`** (you reflashed the card):

```bash
ssh-keygen -R sport-assist.local
ssh sportassist@sport-assist.local
```

Type **`yes`** when asked to trust the new host key.

If **`sport-assist.local` does not resolve**:

1. Open your router’s admin page → DHCP client list.
2. Find **`sport-assist`** and note its IP (e.g. `192.168.1.42`).
3. Connect with:

```bash
ssh sportassist@192.168.1.42
```

Replace `192.168.1.42` with your Pi’s actual IP.

> **Stay in this SSH window** for all **Pi** steps until a section says **Mac**.

---

## 3. Initial system update

**Pi** — paste the whole block:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt autoremove -y
sudo reboot
```

The SSH session will drop. Wait **~90 seconds**.

**Mac** — SSH back in:

```bash
ssh sportassist@sport-assist.local
```

**Check — Pi 5, 64-bit**

**Pi**:

```bash
uname -m
```

Must print: **`aarch64`**

```bash
cat /proc/device-tree/model
free -h
```

Expect **Raspberry Pi 5** and about **3.8 GiB** RAM on a 4 GB board.

---

### 3.1 Pi 5 — active cooler fan

**Pi** — see what is already set:

```bash
CONFIG=/boot/firmware/config.txt
grep -nE '^dtparam=cooling_fan|^dtparam=fan_temp[0-3]' "$CONFIG" || echo '(no fan dtparams yet)'
vcgencmd measure_temp
```

**Pi** — apply fan settings (safe to re-run):

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

Wait ~90 seconds. **Mac** → SSH back in.

**Check**

**Pi**:

```bash
grep -E '^dtparam=cooling_fan|^dtparam=fan_temp0' /boot/firmware/config.txt
vcgencmd measure_temp
```

Expect `cooling_fan=on` and `fan_temp0=60000`.

---

### 3.2 Stay awake — no sleep or display blanking

The poolside unit must never blank the HDMI monitor or suspend.

**Pi**:

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

Wait ~90 seconds. **Mac** → SSH back in.

**Check**

**Pi**:

```bash
grep -E 'consoleblank=0|hdmi_blanking=0' /boot/firmware/cmdline.txt /boot/firmware/config.txt
cat /sys/module/kernel/parameters/consoleblank
```

Last line must print **`0`**.

---

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

Wait ~90 seconds. **Mac** → SSH back in.

**Check**

**Pi**:

```bash
grep -E '^hdmi_enable_4kp60' /boot/firmware/config.txt
```

Expect **`hdmi_enable_4kp60=1`**.

Exact mode lines may need tuning per monitor — see `.cursor/spec-hdmi-output.md`.

---

## 4. Install packages

**Pi**:

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

---

### 4.1 ONVIF (required for camera — install now)

ONVIF libraries are **not** on a fresh Pi. You must copy a file from your Mac first.

#### Step A — copy `requirements-pip.txt` (Mac)

Open a **new Terminal tab** on your Mac (keep the Pi SSH tab open):

```bash
cd <path-to-your-clone>/live-video-delay-replay-system
scp requirements-pip.txt sportassist@sport-assist.local:/home/sportassist/
```

Enter password **`your Imager password`** if asked.

#### Step B — confirm file on Pi

**Pi**:

```bash
ls -la /home/sportassist/requirements-pip.txt
```

Must show a file (not “No such file”).

#### Step C — pip install (Pi)

**Pi**:

```bash
cd /home/sportassist
sudo pip3 install \
  --break-system-packages \
  --ignore-installed isodate \
  --no-binary onvif-zeep \
  -r requirements-pip.txt
```

Wait for **`Successfully installed ... onvif-zeep ...`**.

You can ignore warnings about `types-flask-migrate` or “running pip as root”.

**Pi** — fix WSDL placement (required; `onvif-zeep` often installs WSDL under the wrong `lib/pythonX.Y` path):

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

#### Step D — ONVIF check (Pi)

**Pi** — copy the whole block; it must exit without error:

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

**Check — must see**

```text
onvif import: OK
WSDiscovery import: OK
wsdl: /usr/local/lib/python3.13/site-packages/wsdl
```

(Path may differ slightly — that is fine.)

**If `wsdl: NOT FOUND`** — re-run the **fix WSDL placement** block in Step C, then re-run the check above. To see where pip put the files:

```bash
find /usr/local/lib -name devicemgmt.wsdl 2>/dev/null
python3 -c "import onvif; print(onvif.__file__)"
```

---

### 4.2 Raspberry Pi built-in Wi‑Fi — production AP

The venue **Wi‑Fi AP** (`sport-assist-{serial}`) uses the **Raspberry Pi 5 built-in radio** (`brcmfmac`, typically `wlan0`). No USB Wi‑Fi adapter is required.

**Check — radio present (Pi)**

```bash
iw dev
readlink -f /sys/class/net/wlan*/device/driver 2>/dev/null
rfkill list wifi
```

| Expect                         | Meaning                          |
| ------------------------------ | -------------------------------- |
| A `wlan*` interface            | Built-in Wi‑Fi present           |
| Driver path contains `brcmfmac` | Onboard Broadcom radio           |
| Soft/hard block **no**         | Radio not blocked by `rfkill`    |

`ldrs-wifi-ap.sh` **auto-selects** the built-in interface (`brcmfmac`). Leave **`AP_INTERFACE` unset** in `wifi-ap.env` (§8).

If `iw` shows no interface, confirm the image is Raspberry Pi OS with Wi‑Fi enabled and that `dtoverlay=disable-wifi-pi5` is not in `/boot/firmware/config.txt` (see §4.3).

---

### 4.3 Ensure onboard Wi‑Fi is enabled

Do **not** add `dtoverlay=disable-wifi-pi5` (or legacy `dtoverlay=disable-wifi`). Units upgraded from an older build that disabled the onboard radio should clear those overlays.

**Pi** — after §7 deploy (or anytime before enabling the AP):

```bash
sudo /usr/local/bin/ldrs-ensure-builtin-wifi.sh
# reboot only if the script reports that dtoverlay lines were removed
sudo reboot
```

**Check — after any required reboot (Pi)**

```bash
grep -E 'disable-wifi-pi5|^[[:space:]]*dtoverlay=disable-wifi([[:space:]]|$)' /boot/firmware/config.txt || echo "no wifi-disable overlay (OK)"
iw dev
sudo systemctl restart ldrs-wifi-ap.service
sudo iw dev | grep -E 'type AP|ssid'
```

| Expect                                      | Meaning                    |
| ------------------------------------------- | -------------------------- |
| No `disable-wifi` overlay lines             | Onboard Wi‑Fi available    |
| `wlan*` with driver `brcmfmac`              | Built-in radio in use      |
| `type AP` + your SSID                       | AP on onboard Wi‑Fi        |

---

#### Step E — Wi‑Fi AP prep (Pi)

Bookworm uses **NetworkManager**, which fights `hostapd` unless the AP interface is unmanaged. Production uses the **built-in** `wlan0` radio (§4.2–§4.3).

**Pi**:

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

(`hostapd` / `dnsmasq` are started later by our script — not by Debian defaults.)

---
## 5. Create buffer directories

**Pi**:

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

## 6. Per-unit passwords (Mac)

Each physical unit needs its own Wi‑Fi name/password and settings password. Do this on your **Mac** before copying files to the Pi.

### 6.1 Open the config folder (Mac)

```bash
cd <path-to-your-clone>/live-video-delay-replay-system/config
ls appliance*.env web*.env
```

This repo ships **`*.env.example` only**. Create per-unit files locally (never commit them):

```bash
cp appliance.env.example appliance-UNIT123456.env
cp web.env.example           web-UNIT123456.env
```

The filename suffix (`UNIT123456`) is a label — what matters is **`APPLIANCE_SERIAL`** inside the file (e.g. `UNIT123456` → SSID **`sport-assist-UNIT123456`**).

### 6.2 Edit appliance env (Mac)

```bash
nano appliance-UNIT123456.env
```

Set (example for this unit):

```bash
APPLIANCE_SERIAL=UNIT123456
AP_PSK='ChangeMe-AP-Passphrase'
AP_COUNTRY_CODE=GB
```

- **`AP_PSK`**: minimum **8 characters**.
- **SSID on the Pi will be**: `sport-assist-UNIT123456` (prefix + serial).

Save: **Ctrl+O**, Enter, **Ctrl+X**.

### 6.3 Edit web env (Mac)

```bash
nano web-UNIT123456.env
```

Set values from `config/web.env.example` (field meanings: **`.cursor/spec-settings-page.md` §3**):

```bash
SETTINGS_USERNAME='admin'
SETTINGS_PASSWORD='Your-Web-Login-Password'
SETTINGS_VIEW_PASSWORD='Your-Settings-View-Password'
FLASK_SECRET_KEY='paste-64-char-hex-below'
WEB_SESSION_TIMEOUT=28800
```

**Mac** — generate `FLASK_SECRET_KEY`:

```bash
openssl rand -hex 32
```

Copy the 64-character output into `web-UNIT123456.env`. Save and exit nano.

**Do not commit real passwords to git.**

### 6.4 Write down what you set

| Item                   | Your value                                |
| ---------------------- | ----------------------------------------- |
| Wi‑Fi SSID             | `sport-assist-UNIT123456`                 |
| Wi‑Fi password         | _(your `AP_PSK`)_                         |
| Web username           | `admin` (or your `SETTINGS_USERNAME`)     |
| Web password           | _(your `SETTINGS_PASSWORD`)_              |
| Settings-view password | _(your `SETTINGS_VIEW_PASSWORD`, if set)_ |

You will need these on your **phone** in §10.

---

## 7. Copy `pi-root` to the Pi

Application code, systemd services, and scripts live in the **`pi-root/`** folder. You pack it on the **Mac**, extract on the **Pi**.

### 7.1 Pack and copy (Mac)

**Important:** run this on your **Mac**, not inside the Pi SSH session.

```bash
cd <path-to-your-clone>/live-video-delay-replay-system

COPYFILE_DISABLE=1 tar czf pi-root-sync.tar.gz -C pi-root .
scp pi-root-sync.tar.gz sportassist@sport-assist.local:/home/sportassist/
scp requirements-pip.txt        sportassist@sport-assist.local:/home/sportassist/
scp config/appliance-UNIT123456.env sportassist@sport-assist.local:/home/sportassist/appliance.env
scp config/web-UNIT123456.env       sportassist@sport-assist.local:/home/sportassist/web.env
```

Or use the helper (filename suffix must match `appliance-{SUFFIX}.env`):

```bash
./scripts/push-to-pi.sh UNIT123456
```

### 7.2 Check — files arrived (Pi)

**Pi**:

```bash
ls -la /home/sportassist/pi-root-sync.tar.gz \
       /home/sportassist/requirements-pip.txt \
       /home/sportassist/appliance.env \
       /home/sportassist/web.env
```

All four must exist.

### 7.3 Extract `pi-root` (Pi)

**Pi**:

```bash
sudo tar xzf /home/sportassist/pi-root-sync.tar.gz -C / --no-same-owner --skip-old-files
```

### 7.4 Check — application code (Pi)

**Pi**:

```bash
test -f /home/sportassist/dev/ldrs/lib/onvif_client.py && echo "ldrs: OK" || echo "ldrs: FAIL"
```

Must print **`ldrs: OK`**.

### 7.5 Fix ownership (Pi)

Mac tarballs can break `sudo`. Run **immediately** after extract:

**Pi**:

```bash
sudo /usr/local/bin/ldrs-fix-pi-root-ownership.sh
```

Must print **`pi-root ownership OK`**.

If **`sudo` is already broken** (`/etc/sudoers.d is owned by uid 501`):

**Pi**:

```bash
pkexec chown root:root /etc/sudoers.d
pkexec chmod 755 /etc/sudoers.d
pkexec chown root:root /etc/sudoers.d/sportassist-web
pkexec chmod 440 /etc/sudoers.d/sportassist-web
sudo /usr/local/bin/ldrs-fix-pi-root-ownership.sh
```

### 7.6 Check — ONVIF via project code (Pi)

**Pi**:

```bash
sudo python3 -c "
import sys
sys.path.insert(0, '/home/sportassist/dev/ldrs')
from lib.onvif_client import onvif_wsdl_dir, onvif_available
print('onvif:', onvif_available(), 'wsdl:', onvif_wsdl_dir())
"
```

Must show **`onvif: True`**. If not, return to §4.1.

---

## 8. Merge your passwords into runtime config

This step copies your construction files into `/etc/sportassist/` where services read them.

**Pi** — paste the whole block:

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

**Check — wifi-ap.env looks right (Pi)**

**Pi**:

```bash
grep -E '^AP_SSID=|^APPLIANCE_SERIAL=' /etc/sportassist/wifi-ap.env
```

For this unit you should see:

```text
APPLIANCE_SERIAL=UNIT123456
AP_SSID=sport-assist-UNIT123456
```

If the serial is wrong, fix `appliance-UNIT123456.env` on the Mac, `scp` it to the Pi again, and re-run this §8 block.

---

## 9. Start services and confirm Wi‑Fi AP (critical)

### 9.1 What NOT to do yet

**Do not** run `sudo systemctl enable --now ldrs-network.service` yet.

`ldrs-network` sets **`eth0` to `192.168.10.1`** for the camera. Until the Wi‑Fi AP works, that would leave you with **no SSH** and **no AP**.

### 9.2 Enable services (Pi)

**Before you run this:** `ldrs-usb-hardening.service` builds a USBGuard allowlist from USB devices connected at first run (typically Pi internal hubs). No Wi‑Fi dongle is required.

**Pi**:

```bash
lsusb   # optional — inspect USB topology before enabling hardening

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

### 9.3 Gate — AP must work BEFORE reboot (Pi)

**Pi**:

```bash
sleep 3
sudo systemctl is-active ldrs-wifi-ap.service hostapd dnsmasq ldrs-web.service usbguard.service
sudo iw dev | grep -E 'type AP|ssid'
curl -sS -o /dev/null -w "web login -> %{http_code}\n" http://127.0.0.1:8080/settings/login
sudo usbguard list-devices | head -20
```

**You must see**

| Check                   | Expected                                                                                      |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| `ldrs-wifi-ap.service`  | `active`                                                                                      |
| `hostapd`               | `active`                                                                                      |
| `dnsmasq`               | `active`                                                                                      |
| `usbguard.service`      | `active`                                                                                      |
| `iw dev` (grep AP)      | contains **`type AP`** and **`ssid sport-assist-UNIT123456`** (or your serial) on USB `wlan*` |
| `web login ->`          | `200` or `302`                                                                                |
| `usbguard list-devices` | Pi hubs (and any allowed accessories) listed as **allow** |

**If `hostapd` is `failed` or `inactive`**

**Pi**:

```bash
sudo /usr/local/bin/ldrs-diagnose-ap.sh
sudo /usr/local/bin/ldrs-wifi-ap.sh
```

Read the output. Fix any “Missing …” or “hostapd failed” message, then re-run the gate commands above.

**Do not run `sudo reboot` until `hostapd` is active and `iw` shows the AP.**

### 9.4 Reboot (Pi)

Only when §9.3 passed:

**Pi**:

```bash
sudo reboot
```

Wait **~90 seconds**.

### 9.5 After reboot — quick test (Mac + phone)

**Mac** — SSH should still work (router Ethernet):

```bash
ssh sportassist@sport-assist.local
```

**Pi**:

```bash
sudo systemctl is-active hostapd
sudo iw dev | grep -E 'type AP|ssid' | grep -E 'type AP|ssid'
```

**Phone**

1. Open **Settings → Wi‑Fi**.
2. Look for **`sport-assist-UNIT123456`** (your `sport-assist-{APPLIANCE_SERIAL}`).
3. Tap it → enter **`AP_PSK`** (e.g. `ChangeMe-AP-Passphrase`).
4. Open browser → **`http://192.168.4.1`** → settings login page.

If the SSID does not appear, go to §13 — do **not** continue to §11 until §10 passes.

### 9.6 USB physical security (manufacturing — required before ship)

`ldrs-usb-hardening.service` (enabled in §9.2) does two things on first run:

1. **USBGuard** — allowlist USB devices that were connected when the policy was generated (typically Pi internal hubs). Anything else plugged in later is blocked.
2. **EEPROM** — `ldrs-disable-usb-boot.sh` sets **`BOOT_ORDER=0xf1`** (boot from SD card only; USB mass-storage boot disabled). This takes effect on the **next reboot** (§9.4).

**Pi** — after §9.4 reboot:

```bash
sudo systemctl is-active usbguard.service ldrs-usb-hardening.service
sudo usbguard list-devices
rpi-eeprom-config | grep BOOT_ORDER
test -f /var/lib/sportassist/usbguard-configured && echo 'usbguard stamp: OK'
sudo /usr/local/bin/ldrs-diagnose-ap.sh
```

**You must see**

| Check                       | Expected                                              |
| --------------------------- | ----------------------------------------------------- |
| `usbguard.service`          | `active`                                              |
| `BOOT_ORDER`                | **`0xf1`** (not `0xf461` or other value with USB MSD) |
| `usbguard-configured` stamp | file exists                                           |
| `ldrs-diagnose-ap.sh`       | USB hardening section shows active; built-in Wi‑Fi OK |

**Re-applying USB policy** (field service — plug in any USB accessories that must remain allowed first):

```bash
sudo LDRS_FORCE_USB_HARDENING=1 /usr/local/bin/ldrs-apply-usb-hardening.sh
sudo reboot
```

**Temporary recovery** (bench debug only — plug in USB keyboard, etc.):

```bash
sudo systemctl stop usbguard.service
# when done: sudo systemctl start usbguard.service
```

Do **not** ship a unit until §9.6 passes. Full manufacturing checklist: **§14**.

---

## 10. Verify installation (before camera)

### 10.1 Wi‑Fi AP (phone)

- [ ] Phone shows **Connected** to `sport-assist-UNIT123456`
- [ ] Phone IP is in **`192.168.4.100`–`192.168.4.150`**

### 10.2 Services (Pi)

**Pi**:

```bash
sudo systemctl is-active ldrs-wifi-ap.service hostapd dnsmasq ldrs-web.service ldrs-no-sleep.service usbguard.service
sudo systemctl is-enabled ldrs-network.service ldrs-camera-discovery.service
```

`ldrs-network` and replay services should be **disabled** until §11.

### 10.3 Web UI (phone)

Open **`http://192.168.4.1`**. Log in with **`SETTINGS_USERNAME`** and **`SETTINGS_PASSWORD`** from §6 (default username **`admin`**). After login you should reach **`/replay`**. Opening **`/settings`** may prompt for **`SETTINGS_VIEW_PASSWORD`** if you configured it in §6.

### 10.4 API (Pi or phone browser)

Unauthenticated requests to `/api/status` and `/hls/*` return **401**. After login in the browser, or on the Pi with a session cookie:

**Pi** — quick check (expect **401** without login):

```bash
curl -sS -o /dev/null -w "status unauth -> %{http_code}\n" http://127.0.0.1:8080/api/status
curl -sS -o /dev/null -w "hls unauth -> %{http_code}\n" http://127.0.0.1:8080/hls/live.m3u8
```

Both should print **`401`**. Log in via phone browser (§10.3), then repeat from the phone if needed. HLS → **404** after login is normal until the camera is connected (§11).

**You are done with the base build** when §10 passes. SSH via router still works until §11.

---

## 11. Camera and replay setup

Only after §10 and §9.6 pass.

### 11.1 Bench wiring vs production wiring

| Phase                         | Pi `eth0` cable                     | Settings → Camera Ethernet mode                                   |
| ----------------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| Build / SSH (§2–§10)          | **Home router** (DHCP)              | Leave defaults — do not enable `ldrs-network` yet                 |
| Manufacturing camera test     | **PoE injector → camera** on `eth0` | **Direct to replay unit via PoE Injector**                        |
| Production poolside           | **PoE injector → camera** on `eth0` | **Direct to replay unit via PoE Injector**                        |
| Camera on home LAN (optional) | **Home router**                     | **Customer LAN** — manual camera IP; **Search for camera on LAN** |

**Two subnets (do not mix them up):**

| Network               | Pi address     | Purpose                 |
| --------------------- | -------------- | ----------------------- |
| Wi‑Fi AP (tablets)    | `192.168.4.1`  | Poolside replay UI      |
| Camera Ethernet (PoE) | `192.168.10.1` | Camera DHCP + RTSP only |

Toggling Camera Ethernet mode in Settings **clears** any saved camera IP (avoids stale `192.168.4.x` addresses). In **direct** mode there is **no manual IP field** — use **Save Settings**, then **Refresh camera** after the PoE camera is connected.

**Typical manufacturing workflow:** build on router Ethernet (§2–§10) → join phone to AP → switch `eth0` to PoE injector + camera → Settings → **Direct to replay unit via PoE Injector** → **Save Settings** → **Refresh camera** → **Assign camera**. Power-cycle between router-SSH and PoE-camera tests if needed.

### 11.2 Enable camera and replay

1. Connect the **PoE camera** to Pi **Ethernet** (`eth0`) via PoE injector (production) or home LAN (router mode only).
2. On your **phone** (on the Pi AP), open **`http://192.168.4.1/settings`**.
3. **Camera Ethernet** — select the mode from §11.1 → **Save Settings**.
4. **Refresh camera** (direct mode) or **Search for camera on LAN** (router mode). Use **Clear camera** if you need to wipe credentials/IP before re-assigning.
5. **Assign camera** — use **`admin`** and the **private** password you set in §0 via the camera web UI. Use **Test login** first.
6. **Pi** — enable camera network and replay:

   ```bash
   sudo systemctl enable --now ldrs-network.service
   sudo systemctl enable --now ldrs-camera-discovery.service
   sudo systemctl enable --now ldrs-camera-watch.timer
   sudo systemctl enable --now ldrs-replay-buffer.service
   sudo systemctl enable --now ldrs-hdmi-apply.service
   ```

   **From this point:** `eth0` is **`192.168.10.1`**. SSH via your **home router stops**. Use:
   - Wi‑Fi AP → `ssh sportassist@192.168.4.1` (from a laptop on the AP), or
   - Direct cable → Mac IP **`192.168.10.2`**, then `ssh sportassist@192.168.10.1`

7. **Check RTSP (Pi)**

   ```bash
   set -a; source /etc/sportassist/camera.env; set +a
   ffprobe -hide_banner -rtsp_transport tcp \
     "rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${CAMERA_IP}:554${CAMERA_RTSP_PATH}" 2>&1 | head -20
   ```

8. **Check HLS (Pi)**

   ```bash
   curl -sS http://127.0.0.1:8080/hls/live.m3u8 | head
   ls -la /var/lib/sportassist/hls/
   ls -la /var/lib/sportassist/hls-4k/
   ```

9. **Check HDMI (Pi)** — connect coach monitor if used

   During the first **`LIVE_DELAY_SECONDS`** of warm-up, HDMI should show the idle splash logo (`ldrs-hdmi-idle.service`). Then delayed video replaces it.

   ```bash
   ls -la /usr/share/sportassist/SportAssistLogo.png
   sudo systemctl is-active ldrs-replay-buffer.service ldrs-hdmi-apply.service ldrs-hdmi-idle.service
   sudo /usr/local/bin/ldrs-diagnose-hdmi-delay.sh
   ```

   Expect `mpv` on `http://127.0.0.1:8080/hls-4k/delayed_hdmi.m3u8`, and `delayedHdmiReady: true` in `curl -sS http://127.0.0.1:8080/api/status | jq .delayedHdmiReady` after warm-up.

---

## 12. Updating an already-built Pi

**Mac**:

```bash
cd <path-to-your-clone>/live-video-delay-replay-system
./scripts/push-to-pi.sh UNIT123456
```

**Pi** (SSH via AP `192.168.4.1` or router if `ldrs-network` not enabled):

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
sudo iw dev | grep -E 'type AP|ssid' | grep -E 'type AP|ssid'
sudo rm -f /home/sportassist/pi-root-sync.tar.gz
```

If `/usr/local/bin/ldrs-*.sh` did not change after extract (`--skip-old-files` skips existing files), re-run extract with **`--overwrite`** or copy changed scripts manually, then `sudo systemctl daemon-reload`.

Confirm AP still shows in `iw` before you disconnect.

---

## 13. Troubleshooting

### Cannot SSH

| When                              | What to try                                                                                      |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| §2–§10, Pi on **router Ethernet** | Router DHCP list → `ssh sportassist@<pi-ip>`                                                     |
| After §11 (`ldrs-network` on)     | Phone/laptop on AP → `ssh sportassist@192.168.4.1`, or HDMI keyboard, or cable to `192.168.10.1` |
| Reflashed SD                      | `ssh-keygen -R sport-assist.local` on Mac                                                        |

Default login: **`sportassist`** / **`your Imager password`**

### No Wi‑Fi SSID visible

**Pi** (via SSH or HDMI):

```bash
sudo /usr/local/bin/ldrs-diagnose-ap.sh
sudo systemctl restart ldrs-wifi-ap.service
sudo journalctl -u hostapd -b -n 40 --no-pager
rfkill list
```

| Symptom                   | Fix                                                                 |
| ------------------------- | ------------------------------------------------------------------- |
| `hostapd` failed          | §9.3 — run `ldrs-wifi-ap.sh` in foreground                          |
| `Missing wifi-ap.env`     | Re-run §8                                                           |
| Wrong SSID                | Re-run §8; phone must forget old Wi‑Fi networks                     |
| `rfkill` soft blocked     | `sudo rfkill unblock wifi`                                          |
| Rebooted before AP worked | HDMI or cable to `192.168.10.1` if `ldrs-network` was enabled early |

### Other

| Symptom                                    | Fix                                                                                                                                                           |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sudo: /etc/sudoers.d is owned by uid 501` | §7.5 `ldrs-fix-pi-root-ownership.sh`                                                                                                                          |
| `wsdl: NOT FOUND`                          | §4.1 recovery                                                                                                                                                 |
| `web login -> 000`                         | `sudo journalctl -u ldrs-web -n 30` — check `SETTINGS_USERNAME` / `SETTINGS_PASSWORD` in `web.env`                                                            |
| `pi-root-sync.tar.gz` missing on Pi        | Run §7.1 on **Mac**, not on Pi                                                                                                                                |
| Scripts not updating after §12             | `tar xzf … --overwrite` instead of `--skip-old-files`                                                                                                         |
| HDMI blank (no logo, no video)             | `ls /usr/share/sportassist/SportAssistLogo.png`; `systemctl status ldrs-hdmi-idle`                                                                            |
| HDMI delay wrong / ring not ready          | `sudo /usr/local/bin/ldrs-diagnose-hdmi-delay.sh`                                                                                                             |
| USB keyboard blocked                       | `sudo systemctl stop usbguard.service` (bench only); re-apply policy after adding allowed devices — §9.6                                                      |
| `usbguard` failed after update             | `sudo journalctl -u usbguard -n 30`; ensure `/etc/usbguard/usbguard-daemon.conf` mode `600`                                                                   |
| Camera not found in direct mode            | PoE on `eth0`? **Save Settings** (direct mode) → **Refresh camera**; `grep ETH_CAMERA /etc/sportassist/network.env`; `ip -br addr show eth0` → `192.168.10.1` |
| Stale camera IP after mode change          | **Clear camera** in Settings or toggle Camera Ethernet mode (auto-clears)                                                                                     |

---

## 14. Manufacturing and production

Use this section when building **multiple units** for deployment. Each unit gets unique **`APPLIANCE_SERIAL`**, **`AP_PSK`**, and **`SETTINGS_PASSWORD`** (§6). Record those values on the unit label or build sheet — **do not commit real passwords to git**.

### 14.1 Per-unit build flow

Repeat for every Pi:

| Step               | Section     | Notes                                                                |
| ------------------ | ----------- | -------------------------------------------------------------------- |
| Prepare camera     | §0          | Private admin password; 25 fps; motion/snapshot/audio off            |
| Flash SD + base OS | §1–§5       | Router Ethernet; built-in Wi‑Fi available                        |
| ONVIF + deploy     | §4.1, §6–§8 | Unique `appliance-*.env` / `web-*.env` per serial                |
| AP + USB hardening | §9–§9.6     | `ldrs-usb-hardening`; reboot → `BOOT_ORDER=0xf1`                 |
| Base verification  | §10         | Phone on AP; settings login works                                    |
| Camera commission  | §11         | Direct PoE mode; RTSP + HLS (+ HDMI if fitted)                       |
| Pre-ship gate      | §14.2       | All checks pass before packaging                                     |

### 14.2 Pre-ship checklist

Run on the bench before the unit leaves manufacturing:

- [ ] **Identity** — `APPLIANCE_SERIAL`, Wi‑Fi SSID, `AP_PSK`, `SETTINGS_USERNAME`, `SETTINGS_PASSWORD`, and optional `SETTINGS_VIEW_PASSWORD` recorded for the customer/build sheet
- [ ] **Wi‑Fi AP** — phone joins SSID; `http://192.168.4.1` loads (§10)
- [ ] **USB hardening** — `usbguard.service` active; `BOOT_ORDER=0xf1` (§9.6)
- [ ] **Built-in Wi‑Fi AP** — §4.2–§4.3 (`brcmfmac`; no `disable-wifi-pi5` overlay)
- [ ] **Camera** — §0 web UI settings applied; assigned in Settings with **Direct to replay unit via PoE Injector**
- [ ] **Replay** — `ffprobe` RTSP OK; `/hls/live.m3u8` returns segments; `api/status` shows camera connected
- [ ] **HDMI** (if coach monitor fitted) — logo then delayed video after warm-up (§11.2 step 9)
- [ ] **Diagnostics** — `sudo /usr/local/bin/ldrs-diagnose-ap.sh` — no failures in AP or USB sections
- [ ] **Services** — `ldrs-network`, `ldrs-replay-buffer`, `ldrs-camera-discovery` enabled (post-§11)
- [ ] **Hardware** — official 5 V 5 A PSU; PoE injector packed if supplied separately

### 14.3 Field service and updates

| Task                     | What to do                                                                                                 |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Software update          | §12 — deploy `pi-root-sync.tar.gz`; restart services; confirm AP still up                                  |
| Re-apply USB policy      | Attach allowed USB devices → `sudo LDRS_FORCE_USB_HARDENING=1 /usr/local/bin/ldrs-apply-usb-hardening.sh` → reboot |
| Restore onboard Wi‑Fi    | `sudo /usr/local/bin/ldrs-ensure-builtin-wifi.sh` → reboot if overlays were removed                        |
| Bench debug USB          | `sudo systemctl stop usbguard.service` (re-enable when done)                                               |
| Lost SSH after §11       | Join AP → `ssh sportassist@192.168.4.1`, or cable PC/Mac `192.168.10.2` → `192.168.10.1`                   |
| Full reset               | Reflash SD (§2) and repeat §6–§14 for that serial                                                          |

### 14.4 Production network reference

```text
Tablets / phones  →  Wi‑Fi AP sport-assist-{serial}  →  192.168.4.1  (gateway)
PoE camera        →  Pi eth0                         →  192.168.10.1  (gateway, camera subnet only)
```

Settings password protects the web UI and HLS; Linux password (`sportassist`) is required for SSH. Wi‑Fi clients must **log in** (§6 web credentials) before replay, HLS, or presets.

---

**Canonical behaviour:** `.cursor/architecture-and-technical-spec.md`
