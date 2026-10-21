"""One master, cut to every size (master.py)."""

import itertools
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from studio_helper import master as M
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry
from studio_helper.validators import validate_file

DEFAULTS = Path(__file__).resolve().parents[2] / "defaults" / "registry.yaml"
SIZES = ["ig-story", "ig-post", "mall-screen-veliko-turnovo-led", "web-1240x280",
         "flyer-a4", "mall-print-idea-vinyl-4100x3100", "banner-pair-stacked"]


@pytest.fixture()
def master_job(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    job = job_mod.create_job(jobs, load_registry(DEFAULTS), "Black November", SIZES)
    return jobs, job["id"]


def _picture(path: Path, w: int, h: int) -> Path:
    im = Image.new("RGB", (w, h), (16, 22, 48))
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.4, h * 0.4, w * 0.6, h * 0.6], fill=(255, 196, 0))  # what must stay
    im.save(path)
    return path


def test_each_size_shows_the_most_and_never_cuts_the_box():
    boxes = [[0.4, 0.4, 0.2, 0.2], [0.0, 0.0, 0.3, 0.9], [0.1, 0.45, 0.8, 0.1], [0, 0, 1, 1]]
    frames = [(1080, 1920), (512, 3968), (1240, 280), (1920, 1080), (216, 303)]
    for (mw, mh), box, (dw, dh) in itertools.product([(4000, 3000), (2000, 3000)], boxes, frames):
        f = M.fit(mw, mh, dw, dh, box)
        s = f["s"]
        bx0, by0 = f["left"] + box[0] * mw * s, f["top"] + box[1] * mh * s
        bx1, by1 = bx0 + box[2] * mw * s, by0 + box[3] * mh * s
        assert bx0 >= -1e-6 and by0 >= -1e-6 and bx1 <= dw + 1e-6 and by1 <= dh + 1e-6
        if not f["bands"]:  # the master fills the frame: no edge shows
            assert f["left"] <= 1e-6 and f["top"] <= 1e-6
            assert f["left"] + mw * s >= dw - 1e-6 and f["top"] + mh * s >= dh - 1e-6
            assert s == pytest.approx(max(dw / mw, dh / mh))  # the least zoom that fills


def test_a_tall_strip_from_a_wide_box_gets_the_fill():
    f = M.fit(4000, 3000, 512, 3968, [0.2, 0.3, 0.6, 0.4])
    assert f["bands"] and f["top"] > 0


def test_the_master_is_big_enough_for_every_digital_size(master_job):
    jobs, job_id = master_job
    job = job_mod.load_job(jobs, job_id)
    for app in ("ai", "ps"):
        plan = M.master_size(job, app)
        for fmt in M.cut_sizes(job, app):
            if fmt["kind"] != "print":
                assert max(fmt["size"]["w"] / plan["w"], fmt["size"]["h"] / plan["h"]) <= 1.0001
    ids = {f["id"] for f in M.cut_sizes(job, "ai")}
    assert "flyer-a4" in ids and "mall-print-idea-vinyl-4100x3100" in ids
    # print stays in Illustrator
    assert not {f["id"] for f in M.cut_sizes(job, "ps")} & {"flyer-a4"}
    assert "banner-pair-stacked" not in ids  # panels: by hand
    assert M.master_size(job, "ai")["unit"] == "pt" and M.master_size(job, "ps")["unit"] == "px"


def test_cut_makes_every_digital_size_and_they_pass(master_job, tmp_path):
    jobs, job_id = master_job
    root = job_mod.job_path(jobs, job_id)
    M.update(jobs, job_id, mode="master", app="ps", box=[0.38, 0.38, 0.24, 0.24])
    M.record_made(jobs, job_id, "03_working/x_master_v01.psd", 4000, 3000)
    info = M.take_preview(root, _picture(tmp_path / "m.png", 4000, 3000))
    M.record_preview(jobs, job_id, info)
    res = M.cut_digital(jobs, job_id)
    job = job_mod.load_job(jobs, job_id)
    assert not res["failed"] and not res["kept"]
    assert {m["format_id"] for m in res["made"]} == {
        f["id"] for f in M.cut_sizes(job, "ps")}
    for made in res["made"]:
        result = validate_file(root / made["file"], job)
        assert result.status in ("ok", "warn"), (made, [c.__dict__ for c in result.checks])
    story = Image.open(root / next(m["file"] for m in res["made"] if m["format_id"] == "ig-story"))
    assert story.getpixel((540, 960))[:2] == (255, 196)  # the box is there, in the middle


def test_a_file_she_exported_herself_is_kept(master_job, tmp_path):
    jobs, job_id = master_job
    root = job_mod.job_path(jobs, job_id)
    M.update(jobs, job_id, mode="master", app="ps")
    M.record_preview(jobs, job_id, M.take_preview(root, _picture(tmp_path / "m.png", 2400, 1800)))
    job = job_mod.load_job(jobs, job_id)
    fmt = next(f for f in job["formats"] if f["id"] == "ig-post")
    hers = M.digital_target(job, fmt, root)
    Image.new("RGB", (1080, 1350), "red").save(hers)
    res = M.cut_digital(jobs, job_id)
    assert [k["format_id"] for k in res["kept"]] == ["ig-post"]
    assert Image.open(hers).getpixel((5, 5)) == (255, 0, 0)
    again = M.cut_digital(jobs, job_id)  # ours are replaced, hers still kept
    assert len(again["made"]) == len(res["made"])
    assert [k["format_id"] for k in again["kept"]] == ["ig-post"]
    M.cut_digital(jobs, job_id, overwrite=True)
    assert Image.open(hers).getpixel((5, 5)) != (255, 0, 0)


def test_print_cuts_place_the_master_over_the_bleed(master_job):
    jobs, job_id = master_job
    M.update(jobs, job_id, mode="master", app="ai", box=[0.3, 0.3, 0.4, 0.4])
    M.record_made(jobs, job_id, "03_working/x_master_v01.ai", 4000, 3000)
    cuts = {c["format_id"]: c for c in M.print_cuts(job_mod.load_job(jobs, job_id))}
    a4 = cuts["flyer-a4"]
    assert a4["bleed_mm"] == 3 and not a4["bands"]
    assert a4["x"] <= 0 and a4["y"] <= 0 and a4["x"] + a4["w"] >= 1 and a4["y"] + a4["h"] >= 1
    assert a4["w"] / a4["h"] == pytest.approx((4000 / 3000) * (303 / 216))


def test_settings_are_checked(master_job):
    jobs, job_id = master_job
    with pytest.raises(M.MasterError):
        M.update(jobs, job_id, app="figma")
    with pytest.raises(M.MasterError):
        M.update(jobs, job_id, box=["a", 1, 2, 3])
    job = M.update(jobs, job_id, box=[0.9, 0.9, 0.5, 0.5], format_id="ig-story")
    assert M.section(job)["own"]["ig-story"] == [0.5, 0.5, 0.5, 0.5]  # kept inside
    job = M.update(jobs, job_id, format_id="ig-story", reset=True)
    assert "ig-story" not in M.section(job)["own"]
    M.record_made(jobs, job_id, "03_working/x.ai", 4000, 3000)
    with pytest.raises(M.MasterError):
        M.update(jobs, job_id, app="ps")


def test_reuse_as_new_job_brings_the_master_and_its_box(master_job, tmp_path):
    jobs, job_id = master_job
    root = job_mod.job_path(jobs, job_id)
    M.update(jobs, job_id, mode="master", app="ai", box=[0.2, 0.2, 0.5, 0.5])
    M.update(jobs, job_id, box=[0.1, 0.1, 0.2, 0.2], format_id="ig-story")
    (root / f"03_working/{job_id}_master_v01.ai").write_text("ai")
    M.record_made(jobs, job_id, f"03_working/{job_id}_master_v01.ai", 4000, 3000)
    M.record_preview(jobs, job_id, M.take_preview(root, _picture(tmp_path / "m.png", 400, 300)))
    M.cut_digital(jobs, job_id)
    new = job_mod.reuse_job(jobs, load_registry(DEFAULTS), job_id, "Black Week",
                            ["ig-story", "flyer-a4"])
    m = M.section(new)
    new_root = job_mod.job_path(jobs, new["id"])
    assert m["file"] == f"03_working/{new['id']}_master_v01.ai" and (new_root / m["file"]).is_file()
    assert m["box"] == [0.2, 0.2, 0.5, 0.5] and m["own"] == {"ig-story": [0.1, 0.1, 0.2, 0.2]}
    assert m["cuts"] == {} and (new_root / m["preview"]).is_file()
