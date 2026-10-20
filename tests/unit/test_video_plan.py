from pathlib import Path

import pytest
from studio_helper.core.registry import load_registry
from studio_helper.video import plan

DEFAULTS = load_registry(Path(__file__).parents[2] / "defaults" / "registry.yaml").formats


def job_with(ids, **extra):
    return {"id": "j", "name": "Black November",
            "formats": [dict(DEFAULTS[i], exports=["png", "mp4"]) for i in ids],
            "deliverables": [], **extra}


HER_SCREENS = ["led-screen-1", "led-screen-2", "led-screen-3", "led-screen-4", "led-screen-5",
               "mall-screen-2080x2560", "mall-screen-1280x2240", "mall-screen-1440x1920",
               "mall-screen-416x1248", "mall-screen-paradise-led-column",
               "mall-screen-veliko-turnovo-led", "ig-story", "ig-post"]


def test_her_screens_need_three_masters_and_four_strips():
    p = plan.video_plan(job_with(HER_SCREENS))
    by_ratio = {m["ratio"]: {s["id"] for s in m["screens"]} for m in p["masters"]}
    assert set(by_ratio) == {"9:16", "3:4", "4:3"}
    assert {"led-screen-2", "mall-screen-1280x2240", "ig-story"} <= by_ratio["9:16"]
    assert {"mall-screen-1440x1920", "mall-screen-2080x2560", "ig-post"} <= by_ratio["3:4"]
    assert by_ratio["4:3"] == {"mall-screen-paradise-led-column"}
    assert {s["id"] for s in p["strips"]} == {
        "led-screen-3", "led-screen-4", "mall-screen-416x1248", "mall-screen-veliko-turnovo-led"}


def test_master_minimum_size_covers_every_screen_in_its_group():
    p = plan.video_plan(job_with(["mall-screen-2080x2560", "mall-screen-1440x1920"]))
    m = p["masters"][0]
    assert m["ratio"] == "3:4"
    # 2080 x 2560 needs a 3:4 master at least 2080 wide (and 2560 tall -> 1920 wide)
    assert (m["min_w"], m["min_h"]) == (2080, 2774)


@pytest.mark.parametrize("w,h,expected", [(1080, 1920, 0), (720, 1280, 1)])
def test_upscale_warning(w, h, expected):
    job = job_with(["led-screen-1"])  # 1600 x 2560
    warnings = plan.upscale_warnings(w, h, job)
    assert len(warnings) == expected
    if warnings:
        assert "upscale it in Higgsfield to at least 1600 × 2846" in warnings[0]


def test_reference_pack_copies_only_and_writes_the_plan(tmp_path):
    job = job_with(["ig-story"], pieces=[{"file": "02_assets/pieces/logo.png"}])
    job["deliverables"] = [{"format_id": "ig-story", "type": "png",
                            "expected_stem": "2026-10-20_bn_ig-story_1080x1920px_v01"}]
    (tmp_path / "04_export" / "social").mkdir(parents=True)
    static = tmp_path / "04_export" / "social" / "2026-10-20_bn_ig-story_1080x1920px_v01.png"
    static.write_bytes(b"png")
    (tmp_path / "02_assets" / "pieces").mkdir(parents=True)
    (tmp_path / "02_assets" / "pieces" / "logo.png").write_bytes(b"logo")

    pack, copied = plan.make_reference_pack(job, tmp_path)
    assert sorted(copied) == ["2026-10-20_bn_ig-story_1080x1920px_v01.png", "logo.png"]
    assert static.read_bytes() == b"png"  # original untouched, still there
    readme = (pack / "README.txt").read_text(encoding="utf-8")
    assert "Generate a 9:16 video" in readme
