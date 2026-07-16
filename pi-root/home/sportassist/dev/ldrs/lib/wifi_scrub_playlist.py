#!/usr/bin/env python3
"""Build Wi-Fi HLS playlist with #EXT-X-START at the delayed live edge."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

Segment = Tuple[str, str]


def _parse_playlist(text: str) -> Tuple[List[str], List[Segment]]:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    header: List[str] = []
    segments: List[Segment] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            if i + 1 >= len(lines):
                break
            segments.append((line, lines[i + 1]))
            i += 2
            continue
        if not segments:
            header.append(line)
        i += 1
    return header, segments


def _insert_ext_x_start(header: List[str], seconds_behind_edge: float) -> List[str]:
    start_line = f"#EXT-X-START:TIME-OFFSET=-{seconds_behind_edge:.3f},PRECISE=YES"
    out: List[str] = []
    inserted = False
    for line in header:
        if line.startswith("#EXT-X-START") or line.startswith("#EXT-X-ENDLIST"):
            continue
        out.append(line)
        if line == "#EXTM3U":
            out.append(start_line)
            inserted = True
    if not inserted:
        out = ["#EXTM3U", start_line, *out]
    return out


def _atomic_write(dest: Path, body: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(dest)
    except OSError:
        dest.write_text(body, encoding="utf-8")
        tmp.unlink(missing_ok=True)


def _extinf_seconds(extinf: str) -> float:
    match = re.match(r"#EXTINF:([\d.]+)", extinf)
    return float(match.group(1)) if match else 0.0


def _segments_behind_live_edge(segments: List[Segment], offset_seconds: float) -> List[Segment]:
    """Keep only segments from the delayed live edge to the HLS live edge."""
    offset = max(0.0, float(offset_seconds))
    if offset <= 0 or not segments:
        return segments
    total = 0.0
    kept_rev: List[Segment] = []
    for extinf, uri in reversed(segments):
        kept_rev.append((extinf, uri))
        total += _extinf_seconds(extinf)
        if total >= offset:
            break
    return list(reversed(kept_rev))


def _playlist_header_without_start(header: List[str]) -> List[str]:
    return [
        line
        for line in header
        if not line.startswith("#EXT-X-START") and not line.startswith("#EXT-X-ENDLIST")
    ]


def _write_event_playlist(header: List[str], segments: List[Segment], dest: Path) -> None:
    out_lines: List[str] = []
    has_playlist_type = False
    for line in header:
        if line.startswith("#EXT-X-PLAYLIST-TYPE:"):
            has_playlist_type = True
        out_lines.append(line)
    if not has_playlist_type:
        out_lines.insert(1 if out_lines and out_lines[0] == "#EXTM3U" else 0, "#EXT-X-PLAYLIST-TYPE:EVENT")
    for extinf, uri in segments:
        out_lines.append(extinf)
        out_lines.append(uri)
    _atomic_write(dest, "\n".join(out_lines) + "\n")


def _media_sequence_from_header(header: List[str], default: int = 0) -> int:
    for line in header:
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return default


def _write_hdmi_live_playlist(
    header: List[str],
    all_segments: List[Segment],
    trimmed: List[Segment],
    dest: Path,
) -> None:
    """Sliding live HLS — no EVENT/ENDLIST so mpv keeps polling over HTTP."""
    base_seq = _media_sequence_from_header(header, 0)
    if trimmed:
        first_uri = trimmed[0][1].strip()
        for index, (_, uri) in enumerate(all_segments):
            if uri.strip() == first_uri:
                base_seq += index
                break

    target = 2
    version = 7
    map_line: str | None = None
    start_line: str | None = None
    for line in header:
        if line.startswith("#EXT-X-TARGETDURATION:"):
            try:
                target = max(2, int(float(line.split(":", 1)[1])))
            except ValueError:
                pass
        elif line.startswith("#EXT-X-VERSION:"):
            try:
                version = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("#EXT-X-MAP:"):
            map_line = line
        elif line.startswith("#EXT-X-START:"):
            start_line = line

    out_lines: List[str] = ["#EXTM3U"]
    if start_line:
        out_lines.append(start_line)
    out_lines.extend(
        [
            f"#EXT-X-VERSION:{version}",
            f"#EXT-X-TARGETDURATION:{target}",
            f"#EXT-X-MEDIA-SEQUENCE:{base_seq}",
        ]
    )
    if map_line:
        out_lines.append(map_line)
    for extinf, uri in trimmed:
        out_lines.append(extinf)
        out_lines.append(uri)
    _atomic_write(dest, "\n".join(out_lines) + "\n")


def build_hdmi_delay_playlist(
    source: Path,
    dest: Path,
    start_offset_seconds: float,
) -> bool:
    """Trimmed 4K live HLS — first segment is the delayed edge; mpv starts at index 0."""
    if not source.is_file():
        return False
    header, segments = _parse_playlist(source.read_text(encoding="utf-8", errors="replace"))
    if not segments:
        return False

    media_dir = source.parent
    kept = [seg for seg in segments if (media_dir / seg[1].strip()).is_file()]
    if not kept:
        return False

    trimmed = _segments_behind_live_edge(kept, start_offset_seconds)
    if not trimmed:
        return False

    header_out = _playlist_header_without_start(header)
    _write_hdmi_live_playlist(header_out, kept, trimmed, dest)
    return True


def build_wifi_scrub_playlist(
    source: Path,
    dest: Path,
    start_offset_seconds: float,
) -> bool:
    """Full rolling buffer with #EXT-X-START at the delayed live edge."""
    if not source.is_file():
        return False
    header, segments = _parse_playlist(source.read_text(encoding="utf-8", errors="replace"))
    if not segments:
        return False

    media_dir = source.parent
    kept = [seg for seg in segments if (media_dir / seg[1].strip()).is_file()]
    if not kept:
        return False

    offset = max(0.0, float(start_offset_seconds))
    header_out = _insert_ext_x_start(header, offset)

    _write_event_playlist(header_out, kept, dest)
    return True


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wi-Fi delayed HLS playlist (#EXT-X-START)")
    parser.add_argument("source", type=Path, help="Source live.m3u8")
    parser.add_argument("dest", type=Path, help="Output delayed_sync.m3u8 path")
    parser.add_argument("offset_seconds", type=float, help="Seconds behind the HLS live edge")
    parser.add_argument(
        "--hdmi-trim",
        action="store_true",
        help="Trim playlist from delayed edge (HDMI) instead of full buffer + #EXT-X-START",
    )
    args = parser.parse_args(argv)
    if args.hdmi_trim:
        ok = build_hdmi_delay_playlist(args.source, args.dest, args.offset_seconds)
    else:
        ok = build_wifi_scrub_playlist(args.source, args.dest, args.offset_seconds)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
