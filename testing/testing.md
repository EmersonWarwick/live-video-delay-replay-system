# Manual testing notes (SSH on the Pi)

Use these checks after deploy or when diagnosing venue issues. Run commands **on the Raspberry Pi** over SSH (for example `ssh sportassist@192.168.4.1` from a laptop on the appliance Wi‑Fi AP, or `ssh sportassist@sport-assist.local` when mDNS works).

Related specs: [`.cursor/architecture-and-technical-spec.md`](../.cursor/architecture-and-technical-spec.md) §10, [`.cursor/spec-hls-replay-buffer.md`](../.cursor/spec-hls-replay-buffer.md).

---

## 1. CPU temperature, fan, and throttling

Watch temperature and fan RPM every two seconds:

```bash
watch -n 2 'echo -n "Temp: "; vcgencmd measure_temp; echo -n "Fan: "; cat /sys/devices/platform/cooling_fan/hwmon/hwmon*/fan1_input 2>/dev/null || echo n/a'
```

**Passive cooling:** if the unit has no active cooling fan (heatsink-only or a sealed enclosure), there is **no fan speed to report** — the `Fan:` line will show `n/a` (or the `hwmon` path will be missing). That is expected. Temperature and throttling checks below still apply.

Check whether the SoC has been thermally or power-throttled (`0x0` is healthy):

```bash
vcgencmd get_throttled
```

Optional one-shot readings:

```bash
vcgencmd measure_temp
vcgencmd measure_clock arm
vcgencmd get_mem arm
vcgencmd get_mem gpu
```

---

## 2. Core services

```bash
systemctl is-active \
  ldrs-replay-buffer.service \
  ldrs-hls-delay-playlists.service \
  ldrs-web.service \
  ldrs-hdmi-delay.service \
  ldrs-hdmi-live.service \
  ldrs-hdmi-idle.service \
  ldrs-wifi-ap.service \
  ldrs-network.service \
  ldrs-camera-discovery.service

systemctl status ldrs-replay-buffer.service --no-pager -l
sudo journalctl -u ldrs-replay-buffer.service -n 80 --no-pager
sudo journalctl -u ldrs-web.service -n 40 --no-pager
```

HDMI delay diagnostics:

```bash
sudo /usr/local/bin/ldrs-diagnose-hdmi-delay.sh
```

Wi‑Fi AP diagnostics (when hostapd fails):

```bash
sudo /usr/local/bin/ldrs-diagnose-ap.sh
```

---

## 3. Frame rate and video stream probe (ffprobe)

Load assigned camera credentials, then probe the **main** RTSP stream. Expect about **25 fps**, with width/height matching the configured ladder (often 3840×2160):

```bash
set -a
source /etc/sportassist/camera.env
set +a

ffprobe -hide_banner -rtsp_transport tcp -select_streams v:0 \
  -show_entries stream=codec_name,width,height,avg_frame_rate,r_frame_rate \
  -of default=noprint_wrappers=1 \
  "rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${CAMERA_IP}:${CAMERA_RTSP_PORT:-554}${CAMERA_RTSP_PATH}"
```

Sub stream (1080p Wi‑Fi tier), when configured:

```bash
ffprobe -hide_banner -rtsp_transport tcp -select_streams v:0 \
  -show_entries stream=codec_name,width,height,avg_frame_rate,r_frame_rate \
  -of default=noprint_wrappers=1 \
  "rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${CAMERA_IP}:${CAMERA_RTSP_PORT:-554}${CAMERA_RTSP_PATH_SUB}"
```

Compact JSON (handy for scripting). Report intended **25** fps as `avg_frame_rate` / `r_frame_rate` like `25/1`:

```bash
ffprobe -hide_banner -rtsp_transport tcp -print_format json -show_streams \
  -i "rtsp://${CAMERA_USERNAME}:${CAMERA_PASSWORD}@${CAMERA_IP}:${CAMERA_RTSP_PORT:-554}${CAMERA_RTSP_PATH}" \
  | python3 -c 'import json,sys; s=next(x for x in json.load(sys.stdin)["streams"] if x.get("codec_type")=="video"); print(s.get("width"), "x", s.get("height"), s.get("codec_name"), "avg=", s.get("avg_frame_rate"), "r=", s.get("r_frame_rate"))'
```

Configured ingest values stored after ONVIF assign (may differ slightly from live probe until reconfigure):

```bash
grep -E '^(INGEST_|CAMERA_RTSP_PATH|CAMERA_IP)=' /etc/sportassist/camera.env
```

> Do not paste live camera passwords into tickets or chat logs.

---

## 4. Rolling HLS buffers

Segment directories should gain new `.m4s` files about once per second while delayed mode is active:

```bash
ls -la /var/lib/sportassist/hls/ | tail
ls -la /var/lib/sportassist/hls-4k/ | tail

# Count media segments (order-of-magnitude: ~20 minutes ≈ 1200 s of 1 s segments per tier)
ls /var/lib/sportassist/hls/*.m4s 2>/dev/null | wc -l
ls /var/lib/sportassist/hls-4k/*.m4s 2>/dev/null | wc -l

# Confirm playlists advance (mtime changes)
stat /var/lib/sportassist/hls/live.m3u8 /var/lib/sportassist/hls-4k/live.m3u8
watch -n 2 'stat -c "%y %n" /var/lib/sportassist/hls/live.m3u8 /var/lib/sportassist/hls-4k/live.m3u8'
```

Local playlist fetch (may require a web session cookie once auth is enforced; from the Pi after browser login, or use a session cookie with `curl -b`):

```bash
curl -sS -o /dev/null -w "hls live -> %{http_code}\n" http://127.0.0.1:8080/hls/live.m3u8
curl -sS http://127.0.0.1:8080/hls/live.m3u8 | head
```

Disk use for buffers and root filesystem:

```bash
du -sh /var/lib/sportassist/hls /var/lib/sportassist/hls-4k
df -h /
```

---

## 5. Appliance status JSON

`/api/status` summarises delay, buffer health, and HDMI mode. Unauthenticated calls return **401**; use a logged-in browser session, or pass the session cookie:

```bash
curl -sS -o /dev/null -w "status unauth -> %{http_code}\n" http://127.0.0.1:8080/api/status
# After web login, reuse the cookie jar from your client, e.g.:
# curl -sS -b cookies.txt http://127.0.0.1:8080/api/status | python3 -m json.tool
```

Useful fields once authenticated: `cameraConnected`, `bufferHealth`, `liveDelaySeconds`, `delayedHdmiReady`, `hdmiOutputMode`.

Device generation identifier (no session required):

```bash
curl -sS http://127.0.0.1:8080/device-info
# Expect: {"device":"LDRS2","status":"OK"}
```

---

## 6. Delay and timing configuration

```bash
grep -E '^(LIVE_DELAY_|PIPELINE_LATENCY_|BUFFER_DURATION_|HLS_SEGMENT_|HDMI_OUTPUT_MODE)=' \
  /etc/sportassist/system.env

# Computed playback offset helper (if installed)
python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "/home/sportassist/dev/ldrs")
from lib.env_util import load_env
from lib.delay_util import live_delay_seconds, pipeline_latency_seconds, playback_offset_seconds
e = load_env(Path("/etc/sportassist/system.env"))
print("LIVE_DELAY_SECONDS", live_delay_seconds(e))
print("PIPELINE_LATENCY_SECONDS", pipeline_latency_seconds(e))
print("PLAYBACK_OFFSET", playback_offset_seconds(e))
PY
```

---

## 7. Network snapshot

```bash
ip -br addr
iw dev
systemctl is-active hostapd dnsmasq
hostname
cat /run/sportassist/camera.ip 2>/dev/null || true
```

---

## Suggested soak checklist

1. Temperature / `get_throttled` remain healthy under load (fan RPM only if active cooling is fitted).
2. `ldrs-replay-buffer` stays `active`; HLS `live.m3u8` mtime advances every few seconds.
3. Main RTSP probe reports ~**25 fps** and the expected resolution.
4. After warm-up (`LIVE_DELAY_SECONDS`), HDMI delayed playback is ready; Wi‑Fi clients receive authenticated HLS.
5. 20–30 minute soak: buffers roll (old segments deleted); disk headroom remains comfortable.
