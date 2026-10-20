"""MP4 validator (SPEC.md §6.7): checks the video against the screen's
spec from its headers (mp4info). An MP4 only counts as delivered when
it really is what the screen asked for."""

from __future__ import annotations

from pathlib import Path

from . import match
from .model import Check
from .mp4info import Mp4Error, read_mp4

PLAYABLE_CODECS = {"h264", "hevc", "mpeg4"}


def audio_allowed(fmt: dict) -> bool:
    """Sound is kept on social video (music) and dropped on screens and
    web, unless the format says otherwise."""
    return fmt.get("audio", fmt.get("kind") == "social")


def validate(path: Path, fmt: dict, deliverable: dict) -> list[Check]:
    try:
        info = read_mp4(path)
    except Mp4Error as exc:
        return [Check("readable", "fail", f"Can't read this video: {exc}.",
                      "Export it again and wait until the export has finished.")]
    if not info.has_video:
        return [Check("readable", "fail", "This file has no video in it.",
                      "Export it again; the export may have failed half-way.")]

    checks = [Check("readable", "ok", "Video readable.")]
    checks.append(_check_dimensions(info, fmt, deliverable))
    checks.append(_check_duration(info, fmt))
    checks.append(_check_codec(info))
    checks.append(_check_fps(info, fmt))
    checks.append(_check_audio(info, fmt))
    checks.append(_check_max_kb(path, fmt))
    return checks


def _check_dimensions(info, fmt: dict, deliverable: dict) -> Check:
    w, h = (round(v) for v in match.deliverable_size(fmt, deliverable))
    if (info.width, info.height) != (w, h):
        return Check("dimensions", "fail",
                     f"This video is {info.width}×{info.height}px; expected {w}×{h}px.",
                     "Export it again at the exact pixel size of this screen.")
    return Check("dimensions", "ok", f"{w}×{h}px, as expected.")


def _check_duration(info, fmt: dict) -> Check:
    secs = info.duration_s
    limit = fmt.get("max_duration_s")
    if limit and secs > limit + 0.05:
        return Check("duration", "fail",
                     f"This video is {secs:.1f}s; this screen takes at most {limit:g}s.",
                     f"Trim it to {limit:g} seconds or less.")
    if secs < 1:
        return Check("duration", "warn", f"This video is only {secs:.1f}s long.",
                     "Check that the whole video was exported.")
    if limit:
        return Check("duration", "ok", f"{secs:.1f}s, within the {limit:g}s limit.")
    return Check("duration", "ok", f"{secs:.1f}s long.")


def _check_codec(info) -> Check:
    if info.codec == "av1":
        return Check("codec", "warn", "This video is AV1; many LED players can't play it.",
                     "Export as H.264 unless the screen operator asked for AV1.")
    if info.codec not in PLAYABLE_CODECS:
        return Check("codec", "fail", f"This video uses '{info.codec}', which screens don't play.",
                     "Export as H.264 (MP4).")
    return Check("codec", "ok", f"Codec {info.codec.upper()}.")


def _check_fps(info, fmt: dict) -> Check:
    want = fmt.get("fps")
    if not want:
        return Check("fps", "ok", f"{info.fps:g} frames per second." if info.fps
                     else "Frame rate not stated in the file.")
    if abs(info.fps - want) > 0.01 * want:
        return Check("fps", "fail",
                     f"This video is {info.fps:g} fps; this screen needs {want:g} fps.",
                     f"Export it again at {want:g} frames per second.")
    return Check("fps", "ok", f"{info.fps:g} fps, as required.")


def _check_audio(info, fmt: dict) -> Check:
    if info.has_audio and not audio_allowed(fmt):
        return Check("audio", "warn", "This video has sound; screens play it silent.",
                     "Fine to send, but you can export without sound to make the file smaller.")
    return Check("audio", "ok", "Has sound." if info.has_audio else "No sound.")


def _check_max_kb(path: Path, fmt: dict) -> Check:
    max_kb = fmt.get("max_kb")
    size_kb = path.stat().st_size / 1024
    if not max_kb:
        return Check("file-size", "ok", f"{size_kb / 1024:.1f}MB.")
    if size_kb > max_kb:
        return Check("file-size", "fail",
                     f"This video is {size_kb / 1024:.1f}MB; this screen takes at most "
                     f"{max_kb / 1024:.0f}MB.",
                     "Export it again at a lower quality, or shorten it.")
    return Check("file-size", "ok",
                 f"{size_kb / 1024:.1f}MB, within the {max_kb / 1024:.0f}MB limit.")
