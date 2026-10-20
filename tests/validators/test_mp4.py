import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from conftest import status_of  # noqa: E402
from mp4_fixture import make_mp4  # noqa: E402
from studio_helper.validators import mp4  # noqa: E402
from studio_helper.validators.mp4info import Mp4Error, read_mp4  # noqa: E402

VT = {
    "id": "mall-screen-veliko-turnovo-led",
    "kind": "screen",
    "size": {"w": 512, "h": 3968, "unit": "px"},
    "exports": ["jpg", "mp4"],
    "max_kb": 30720,
    "max_duration_s": 20,
}
DELIVERABLE = {"format_id": VT["id"], "type": "mp4", "panel": None}


def test_signature_matches_other_validators():
    import inspect

    assert list(inspect.signature(mp4.validate).parameters) == ["path", "fmt", "deliverable"]


def test_good_screen_video_is_all_ok(tmp_path):
    f = make_mp4(tmp_path / "ok.mp4", w=512, h=3968, seconds=15, fps=25)
    checks = mp4.validate(f, VT, DELIVERABLE)
    assert all(c.status == "ok" for c in checks), checks
    assert {c.id for c in checks} == {
        "readable", "dimensions", "duration", "codec", "fps", "audio", "file-size"}


@pytest.mark.parametrize("content", [b"", b"not a real mp4", b"\x00\x00\x00\x08ftyp"])
def test_empty_or_broken_file_fails_not_delivered(tmp_path, content):
    f = tmp_path / "broken.mp4"
    f.write_bytes(content)
    checks = mp4.validate(f, VT, DELIVERABLE)
    assert status_of(checks, "readable") == "fail"


def test_truncated_export_without_moov_fails(tmp_path):
    full = make_mp4(tmp_path / "full.mp4", moov_last=True).read_bytes()
    cut = tmp_path / "cut.mp4"
    cut.write_bytes(full[: len(full) // 2])
    assert status_of(mp4.validate(cut, VT, DELIVERABLE), "readable") == "fail"


def test_wrong_size_fails(tmp_path):
    f = make_mp4(tmp_path / "x.mp4", w=1080, h=1920)
    assert status_of(mp4.validate(f, VT, DELIVERABLE), "dimensions") == "fail"


def test_too_long_fails_and_short_warns(tmp_path):
    long = make_mp4(tmp_path / "long.mp4", seconds=25)
    assert status_of(mp4.validate(long, VT, DELIVERABLE), "duration") == "fail"
    short = make_mp4(tmp_path / "short.mp4", seconds=0.5)
    assert status_of(mp4.validate(short, VT, DELIVERABLE), "duration") == "warn"


def test_sound_warns_on_screens_but_not_where_allowed(tmp_path):
    f = make_mp4(tmp_path / "a.mp4", audio=True)
    assert status_of(mp4.validate(f, VT, DELIVERABLE), "audio") == "warn"
    assert status_of(mp4.validate(f, dict(VT, audio=True), DELIVERABLE), "audio") == "ok"


@pytest.mark.parametrize("codec,expected", [
    ("h264", "ok"), ("hevc", "ok"), ("mpeg4", "ok"), ("av1", "warn"), ("prores", "fail")])
def test_codecs(tmp_path, codec, expected):
    f = make_mp4(tmp_path / f"{codec}.mp4", codec=codec)
    assert status_of(mp4.validate(f, VT, DELIVERABLE), "codec") == expected


def test_required_fps(tmp_path):
    f = make_mp4(tmp_path / "f.mp4", fps=30)
    assert status_of(mp4.validate(f, dict(VT, fps=25), DELIVERABLE), "fps") == "fail"
    assert status_of(mp4.validate(f, dict(VT, fps=30), DELIVERABLE), "fps") == "ok"


def test_over_max_kb_fails(tmp_path):
    f = make_mp4(tmp_path / "big.mp4", padding_bytes=40 * 1024)
    assert status_of(mp4.validate(f, dict(VT, max_kb=10), DELIVERABLE), "file-size") == "fail"


def test_reads_moov_after_mdat_and_64bit_sizes(tmp_path):
    f = make_mp4(tmp_path / "late.mp4", moov_last=True, large_mdat=True, tkhd_version=1,
                 w=1920, h=1440, seconds=10, fps=30, audio=True)
    info = read_mp4(f)
    assert (info.width, info.height) == (1920, 1440)
    assert info.duration_s == pytest.approx(10)
    assert info.fps == pytest.approx(30)
    assert info.codec == "h264" and info.has_audio and info.has_video


def test_read_mp4_rejects_non_mp4(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"\x00" * 64)
    with pytest.raises(Mp4Error):
        read_mp4(f)
