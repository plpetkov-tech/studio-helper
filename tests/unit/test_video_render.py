"""Video rendering (ROADMAP R5-R7) against a fake Concat that speaks the
real 0.2.8 tool list, so CI needs no Concat. Set STUDIO_HELPER_CONCAT=1
to run the last test against the Concat installed on this machine."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry
from studio_helper.validators import validate_file
from studio_helper.video import concat as C
from studio_helper.video import recipes, service

FIX = Path(__file__).resolve().parents[1] / "fixtures"
sys.path.insert(0, str(FIX))
from mp4_fixture import make_mp4  # noqa: E402

FAKE = [sys.executable, str(FIX / "fake_concat.py")]
DEFAULTS = Path(__file__).resolve().parents[2] / "defaults" / "registry.yaml"


@pytest.fixture()
def video_job(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    reg = load_registry(DEFAULTS)
    job = job_mod.create_job(jobs, reg, "Black November",
                             ["ig-story", "mall-screen-veliko-turnovo-led",
                              "mall-screen-paradise-led-column"])
    root = jobs / job["id"]
    for d in job["deliverables"]:
        if d["type"] in ("png", "jpg"):
            fmt = next(f for f in job["formats"] if f["id"] == d["format_id"])
            sub = {"social": "social", "screen": "led"}[fmt["kind"]]
            Image.new("RGB", (fmt["size"]["w"], fmt["size"]["h"])).save(
                root / "04_export" / sub / f"{d['expected_stem']}.{d['type']}")
    master = make_mp4(tmp_path / "higgsfield_9x16.mp4", w=1080, h=1920, seconds=8, fps=24,
                      audio=True)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (600, 200), (255, 255, 255, 255)).save(logo)
    return jobs, job["id"], master, logo


def test_concat_session_checks_the_tools_it_needs():
    with C.ConcatSession([Path.cwd()], command=FAKE) as c:
        assert c.version == "0.2.8"


def test_a_renamed_tool_is_a_plain_message(monkeypatch):
    monkeypatch.setitem(C.TOOLS_USED, "clip_transform", {"path", "clipId", "zoom"})
    with pytest.raises(C.ConcatError, match="isn't supported yet.*clip_transform"):
        with C.ConcatSession([Path.cwd()], command=FAKE):
            pass


def test_find_concat_uses_a_configured_path(tmp_path):
    exe = tmp_path / "concat.exe"
    exe.write_bytes(b"")
    assert C.find_concat(str(exe)) == exe


def test_master_is_copied_and_probed(video_job):
    jobs, job_id, master, _ = video_job
    job, _warnings = service.add_master(jobs, job_id, master)
    m = job["video"]["masters"][0]
    assert (m["w"], m["h"], m["fps"]) == (1080, 1920, 24)
    assert m["file"] == "02_assets/video/higgsfield_9x16.mp4"
    assert master.exists()  # her original stays where it was


def test_render_all_makes_every_video_size_and_they_pass_the_checks(video_job, tmp_path):
    jobs, job_id, master, logo = video_job
    service.add_master(jobs, job_id, master)
    service.add_piece(jobs, job_id, logo, "Logo")
    service.set_juice(jobs, job_id, "m1", [{"t": 0, "box": [0.25, 0.3, 0.5, 0.3]}])
    service.set_screen(jobs, job_id, "mall-screen-paradise-led-column", mode="motion")
    log = tmp_path / "calls.jsonl"
    progress = []
    os.environ["FAKE_CONCAT_LOG"] = str(log)
    try:
        result = service.render_all(jobs, job_id, report=progress.append, concat_command=FAKE)
    finally:
        os.environ.pop("FAKE_CONCAT_LOG")
    assert result["failed"] == [] and len(result["rendered"]) == 3
    job = job_mod.load_job(jobs, job_id)
    root = jobs / job_id
    for fid, r in job["video"]["renders"].items():
        res = validate_file(root / r["file"], job)
        assert res.status == "ok", (fid, [(c.id, c.message) for c in res.checks])
    assert job["video"]["renders"]["mall-screen-paradise-led-column"]["mode"] == "motion"
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    # screens are silent; the story keeps its sound
    muted = [c for c in calls if c["tool"] == "clip_update" and c["args"]["patch"].get("muted")]
    assert len(muted) == 1
    assert progress[-1]["done"] == progress[-1]["total"] == 3


def test_a_video_she_made_herself_is_never_overwritten(video_job):
    jobs, job_id, master, _ = video_job
    service.add_master(jobs, job_id, master)
    job = job_mod.load_job(jobs, job_id)
    stem = next(d["expected_stem"] for d in job["deliverables"]
                if d["format_id"] == "ig-story" and d["type"] == "mp4")
    hers = jobs / job_id / "04_export" / "social" / f"{stem}.mp4"
    hers.write_bytes(b"from DaVinci")
    result = service.render_all(jobs, job_id, format_ids=["ig-story"], concat_command=FAKE)
    assert result["rendered"] == [] and "wasn't made here" in result["skipped"][0]["reason"]
    assert hers.read_bytes() == b"from DaVinci"


def test_rerender_moves_the_old_project_aside(video_job):
    jobs, job_id, master, _ = video_job
    service.add_master(jobs, job_id, master)
    for _ in range(2):
        service.render_all(jobs, job_id, format_ids=["ig-story"], concat_command=FAKE)
    names = sorted(p.name for p in (jobs / job_id / "03_working" / "video").iterdir())
    assert names[0] == "ig-story" and names[1].startswith("ig-story.previous-")


def test_only_one_render_at_a_time(video_job):
    jobs, job_id, _, _ = video_job
    assert service._render_lock.acquire(blocking=False)
    try:
        with pytest.raises(service.VideoError, match="already being made"):
            service.render_all(jobs, job_id, concat_command=FAKE)
    finally:
        service._render_lock.release()


def test_pieces_stack_inside_the_story_safe_area(video_job, tmp_path):
    jobs, job_id, _, logo = video_job
    line = tmp_path / "line.png"
    Image.new("RGBA", (900, 120)).save(line)
    service.add_piece(jobs, job_id, logo, "Logo")
    service.add_piece(jobs, job_id, line, "Promo line")
    job = job_mod.load_job(jobs, job_id)
    story = next(f for f in job["formats"] if f["id"] == "ig-story")
    layers = recipes.piece_layers(job, story, jobs / job_id, end_s=8)
    assert len(layers) == 2
    logo_l, line_l = layers
    assert logo_l.start < line_l.start  # one after another
    assert logo_l.offset_y < line_l.offset_y  # logo above its line
    # the line's bottom stays above Instagram's bottom bar (340 px)
    bottom_px = 960 + line_l.offset_y * 1920 + (22 / 100 * 1080 * 120 / 900) / 2
    assert bottom_px <= 1920 - 340


def test_piece_validation(video_job):
    jobs, job_id, _, logo = video_job
    service.add_piece(jobs, job_id, logo)
    with pytest.raises(service.VideoError):
        service.update_piece(jobs, job_id, "p1", {"anchor": "upside-down"})
    with pytest.raises(service.VideoError):
        service.add_piece(jobs, job_id, logo.with_suffix(".svg"))


@pytest.mark.skipif(not (os.environ.get("STUDIO_HELPER_CONCAT") and shutil.which("concat")),
                    reason="set STUDIO_HELPER_CONCAT=1 with Concat installed")
def test_real_concat_renders_a_checked_video(video_job, tmp_path):
    jobs, job_id, _, _ = video_job
    env = {k: str(tmp_path / "concat-home" / k.lower()) for k in
           ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")}
    service.set_screen(jobs, job_id, "mall-screen-paradise-led-column", mode="motion")
    result = service.render_all(jobs, job_id, format_ids=["mall-screen-paradise-led-column"],
                                concat_env=env)
    assert result["failed"] == [], result
    job = job_mod.load_job(jobs, job_id)
    r = job["video"]["renders"]["mall-screen-paradise-led-column"]
    assert validate_file(jobs / job_id / r["file"], job).status == "ok"
