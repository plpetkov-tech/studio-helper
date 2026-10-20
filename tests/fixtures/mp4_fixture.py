"""Builds tiny MP4 files with chosen headers for the video validator
tests. No picture is encoded: the validator only reads box headers,
so the 'mdat' payload is filler bytes."""

from __future__ import annotations

import struct
from pathlib import Path

FOURCC = {"h264": b"avc1", "hevc": b"hvc1", "av1": b"av01", "mpeg4": b"mp4v", "prores": b"apch"}


def box(kind: bytes, payload: bytes, *, large: bool = False) -> bytes:
    if large:
        return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _full(version: int = 0) -> bytes:
    return bytes([version, 0, 0, 0])


def _mvhd(timescale: int, duration: int) -> bytes:
    return box(b"mvhd", _full() + struct.pack(">IIII", 0, 0, timescale, duration) + bytes(80))


def _tkhd(w: int, h: int, version: int = 0) -> bytes:
    if version == 1:
        head = _full(1) + struct.pack(">QQIIQ", 0, 0, 1, 0, 0)
    else:
        head = _full() + struct.pack(">IIIII", 0, 0, 1, 0, 0)
    tail = bytes(8) + bytes(8) + bytes(36) + struct.pack(">II", w << 16, h << 16)
    return box(b"tkhd", head + tail)


def _mdhd(timescale: int, duration: int) -> bytes:
    return box(b"mdhd", _full() + struct.pack(">IIII", 0, 0, timescale, duration) + bytes(4))


def _hdlr(handler: bytes) -> bytes:
    return box(b"hdlr", _full() + bytes(4) + handler + bytes(12) + b"\0")


def _stsd(fourcc: bytes) -> bytes:
    entry = struct.pack(">I4s", 16, fourcc) + bytes(8)
    return box(b"stsd", _full() + struct.pack(">I", 1) + entry)


def _stts(samples: int, delta: int) -> bytes:
    return box(b"stts", _full() + struct.pack(">III", 1, samples, delta))


def _trak(handler: bytes, w: int, h: int, timescale: int, duration: int,
          fourcc: bytes, samples: int, delta: int, tkhd_version: int = 0) -> bytes:
    stbl = box(b"stbl", _stsd(fourcc) + _stts(samples, delta))
    minf = box(b"minf", stbl)
    mdia = box(b"mdia", _mdhd(timescale, duration) + _hdlr(handler) + minf)
    return box(b"trak", _tkhd(w, h, tkhd_version) + mdia)


def make_mp4(
    dest: Path,
    *,
    w: int = 512,
    h: int = 3968,
    seconds: float = 15.0,
    fps: int = 25,
    codec: str = "h264",
    audio: bool = False,
    moov_last: bool = False,
    large_mdat: bool = False,
    tkhd_version: int = 0,
    padding_bytes: int = 1024,
) -> Path:
    timescale = fps * 1000
    samples = round(seconds * fps)
    duration = samples * 1000
    traks = _trak(b"vide", w, h, timescale, duration, FOURCC.get(codec, codec.encode()),
                  samples, 1000, tkhd_version)
    if audio:
        traks += _trak(b"soun", 0, 0, 48000, round(seconds * 48000), b"mp4a",
                       round(seconds * 48000 / 1024), 1024)
    moov = box(b"moov", _mvhd(1000, round(seconds * 1000)) + traks)
    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomavc1")
    mdat = box(b"mdat", bytes(padding_bytes), large=large_mdat)
    parts = [ftyp, mdat, moov] if moov_last else [ftyp, moov, mdat]
    dest.write_bytes(b"".join(parts))
    return dest
