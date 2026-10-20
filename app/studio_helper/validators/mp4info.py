"""Reads what a video file is from its MP4/MOV box headers: size, length,
frame rate, codec, sound. Pure Python, no FFmpeg (SPEC.md §2.4), and it
never reads the picture data: it seeks from box to box, so a 250 MB
file costs a few kilobytes of reads.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

# Boxes that only hold other boxes, on the path to what we read.
_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts"}

CODEC_NAMES = {
    b"avc1": "h264", b"avc3": "h264",
    b"hvc1": "hevc", b"hev1": "hevc",
    b"av01": "av1",
    b"mp4v": "mpeg4",
    b"vp09": "vp9",
}


class Mp4Error(ValueError):
    pass


@dataclass
class Track:
    handler: str = ""  # "vide", "soun", ...
    width: float = 0.0
    height: float = 0.0
    timescale: int = 0
    duration: int = 0
    codec: str = ""
    sample_count: int = 0


@dataclass
class Mp4Info:
    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""  # "h264", "hevc", "av1", "mpeg4", or the raw fourcc
    has_audio: bool = False
    has_video: bool = False
    tracks: list[Track] = field(default_factory=list)


def _boxes(f: BinaryIO, start: int, end: int):
    """(type, payload start, payload end) for each box in [start, end)."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        header = f.read(8)
        if len(header) < 8:
            return
        size, kind = struct.unpack(">I4s", header)
        payload = pos + 8
        if size == 1:  # 64-bit size follows the type
            big = f.read(8)
            if len(big) < 8:
                return
            size = struct.unpack(">Q", big)[0]
            payload = pos + 16
        elif size == 0:  # runs to the end of the enclosing space
            size = end - pos
        if size < payload - pos:
            raise Mp4Error(f"broken '{kind.decode('latin-1')}' box")
        yield kind, payload, min(pos + size, end)
        pos += size


def _read(f: BinaryIO, at: int, n: int) -> bytes:
    f.seek(at)
    data = f.read(n)
    if len(data) < n:
        raise Mp4Error("file ends inside a header")
    return data


def _full_box_version(f: BinaryIO, at: int) -> int:
    return _read(f, at, 1)[0]


def _walk_track(f: BinaryIO, start: int, end: int, track: Track) -> None:
    for kind, a, b in _boxes(f, start, end):
        if kind in _CONTAINERS:
            _walk_track(f, a, b, track)
        elif kind == b"tkhd":
            v = _full_box_version(f, a)
            # width/height are the last 8 bytes, 16.16 fixed point
            w, h = struct.unpack(">II", _read(f, a + (84 if v == 1 else 72) + 4, 8))
            track.width, track.height = w / 65536, h / 65536
        elif kind == b"mdhd":
            v = _full_box_version(f, a)
            if v == 1:
                track.timescale, track.duration = struct.unpack(">IQ", _read(f, a + 20, 12))
            else:
                track.timescale, track.duration = struct.unpack(">II", _read(f, a + 12, 8))
        elif kind == b"hdlr":
            track.handler = _read(f, a + 8, 4).decode("latin-1")
        elif kind == b"stsd":
            # version/flags (4) + entry count (4), then the first entry: size (4) + format (4)
            fourcc = _read(f, a + 12, 4)
            track.codec = CODEC_NAMES.get(fourcc, fourcc.decode("latin-1").strip())
        elif kind == b"stts":
            (count,) = struct.unpack(">I", _read(f, a + 4, 4))
            count = min(count, (b - a - 8) // 8)
            table = _read(f, a + 8, count * 8)
            track.sample_count = sum(n for n, _delta in struct.iter_unpack(">II", table))


def read_mp4(path: Path) -> Mp4Info:
    """Raises Mp4Error when the file isn't a readable MP4/MOV."""
    size = path.stat().st_size
    info = Mp4Info()
    with path.open("rb") as f:
        moov = next(((a, b) for kind, a, b in _boxes(f, 0, size) if kind == b"moov"), None)
        if moov is None:
            raise Mp4Error("no 'moov' header: the export didn't finish, or this isn't an MP4")
        for kind, a, b in _boxes(f, *moov):
            if kind == b"mvhd":
                v = _full_box_version(f, a)
                if v == 1:
                    scale, dur = struct.unpack(">IQ", _read(f, a + 20, 12))
                else:
                    scale, dur = struct.unpack(">II", _read(f, a + 12, 8))
                info.duration_s = dur / scale if scale else 0.0
            elif kind == b"trak":
                track = Track()
                _walk_track(f, a, b, track)
                info.tracks.append(track)

    video = next((t for t in info.tracks if t.handler == "vide"), None)
    info.has_audio = any(t.handler == "soun" for t in info.tracks)
    if video:
        info.has_video = True
        info.width, info.height = round(video.width), round(video.height)
        info.codec = video.codec
        if video.timescale and video.duration:
            track_s = video.duration / video.timescale
            if not info.duration_s:
                info.duration_s = track_s
            if video.sample_count:
                info.fps = round(video.sample_count / track_s, 3)
    return info
