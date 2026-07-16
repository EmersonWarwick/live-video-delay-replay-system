# Spec: Capture / FFmpeg (v2)

**Role in v2**: ffmpeg on the Raspberry Pi 5 **ingests camera RTSP** and **remuxes** to fMP4 HLS segments for the 20-minute rolling buffer.

There is **no USB/V4L2 capture** on Pi. The camera is **programmed via ONVIF** to output the correct codec, resolution, frame rate, and GOP before ingest.

---

## Canonical documents

| Topic                       | Spec                             |
| --------------------------- | -------------------------------- |
| ONVIF stream configuration  | `spec-camera-stream-profiles.md` |
| RTSP input                  | `spec-rtsp-ingest.md`            |
| HLS/fMP4 output + retention | `spec-hls-replay-buffer.md`      |
| HTTP serving                | `spec-api-endpoints.md`          |

---

## ffmpeg responsibilities

| Task                                                 | Allowed                                                 |
| ---------------------------------------------------- | ------------------------------------------------------- |
| Read camera RTSP main + sub (TCP)                    | **Yes** — Pi only                                       |
| Remux H.264/H.265 to fMP4 HLS (`-c:v copy`)          | **Required** — default path (dual: 4K main + 1080p sub) |
| Transcode scale/encode on Pi                         | **Forbidden in production** unless documented exception |
| Write rolling 20 min HLS segments (1 s, GOP-aligned) | **Yes**                                                 |
| Serve HTTP to Android                                | **No** — `ldrs-web` serves files                        |

---

## Design rule

**Camera encodes → Pi remuxes.** Do not use Pi ffmpeg to fix a misconfigured camera — use ONVIF `SetVideoEncoderConfiguration` instead.

Hardware transcode (`h264_v4l2m2m`) may be used **only if** remux is impossible and soak tests pass — exception must be recorded.

---

## Out of scope

| Task                                  | Reason                                    |
| ------------------------------------- | ----------------------------------------- |
| ffmpeg on Android for replay buffer   | Android thin client                       |
| WebRTC-to-disk as main archive        | Not agreed architecture                   |
| USB `h264_v4l2m2m` from `/dev/video0` | v1 / MobileReplaySystem — not v2          |
| MediaMTX as 20 min buffer owner       | See `spec-hls-replay-buffer.md`           |
| Pi scale 4K→1080p for Wi‑Fi           | Use camera **sub stream** @ 1080p instead |

---

## MobileReplaySystem note

Do not copy `sportassist-capture-ffmpeg.sh` USB pipeline into v2. v2 ffmpeg reads **network RTSP** from ONVIF-configured profiles, not V4L2.
