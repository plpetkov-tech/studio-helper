"""Figma-style motion (video/motion.py) and motion from statics
(video/recipes.py): easing curves, springs, transitions, brand-piece
entrances, the Video tab's settings and the live preview data."""

from pathlib import Path

import pytest
from PIL import Image
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry
from studio_helper.video import motion as M
from studio_helper.video import recipes, service

DEFAULTS = Path(__file__).resolve().parents[2] / "defaults" / "registry.yaml"


# -- curves and springs ---------------------------------------------------------------


def test_bezier_curves_match_css():
    assert M.bezier_value(M.CURVES["linear"], 0.3) == pytest.approx(0.3, abs=1e-6)
    assert M.bezier_value(M.CURVES["ease-in-out"], 0.5) == pytest.approx(0.5, abs=1e-4)
    half = {k: M.bezier_value(M.CURVES[k], 0.5) for k in ("ease-out", "ease-in")}
    assert half["ease-out"] > 0.5 > half["ease-in"]
    # back curves overshoot
    assert max(M.bezier_value(M.CURVES["ease-out-back"], u / 100) for u in range(100)) > 1
    assert min(M.bezier_value(M.CURVES["ease-in-back"], u / 100) for u in range(100)) < 0


def test_figma_spring_presets_feel_different():
    d = {k: M.spring_duration(p) for k, p in M.SPRINGS.items()}
    assert d["quick"] < d["gentle"] < d["slow"]
    peak = {k: max(M.spring_value(p, t / 100) for t in range(300)) for k, p in M.SPRINGS.items()}
    assert peak["bouncy"] > 1.2      # bounces past its place
    assert peak["slow"] <= 1.0001    # settles without overshoot
    for p in M.SPRINGS.values():
        assert M.spring_value(p, 0) == pytest.approx(0, abs=1e-9)
        assert M.spring_value(p, M.spring_duration(p)) == pytest.approx(1, abs=M.SETTLE * 1.5)


def test_heavier_mass_is_slower_and_swings_further():
    light = {"mass": 1, "stiffness": 100, "damping": 15}
    heavy = {"mass": 3, "stiffness": 100, "damping": 15}
    assert M.spring_duration(heavy) > M.spring_duration(light)
    assert (max(M.spring_value(heavy, t / 100) for t in range(400))
            > max(M.spring_value(light, t / 100) for t in range(400)))


def test_easing_is_checked():
    assert M.clean_easing(None) == {"type": "gentle"}
    assert M.clean_easing("bouncy") == {"type": "bouncy"}
    custom = M.clean_easing({"type": "spring", "mass": 2})
    assert custom == {"type": "spring", "mass": 2.0, "stiffness": 100.0, "damping": 15.0}
    for bad in ({"type": "wobbly"}, {"type": "spring", "mass": 0},
                {"type": "spring", "damping": "lots"}, {"type": "bezier", "points": [2, 0, 1, 1]},
                {"type": "bezier", "points": [0, 0, 1]}):
        with pytest.raises(M.MotionError):
            M.clean_easing(bad)


# -- keyframes --------------------------------------------------------------------------


def test_a_lone_curve_is_two_keys_with_the_curve_on_the_second():
    segs = [M.Seg("scale", 1.0, 2.0, 1.0, 1.2, {"type": "ease-out"})]
    keys = M.keys_for("scale", 1.0, segs, 8.0)
    assert keys == [{"property": "scale", "at": 0.125, "value": 1.0},
                    {"property": "scale", "at": 0.375, "value": 1.2, "ease": [0, 0, 0.58, 1]}]


def test_a_spring_is_sampled_and_lands_exactly():
    segs = [M.Seg("offsetY", 0.0, M.spring_duration(M.SPRINGS["bouncy"]), 0.1, 0.0,
                  {"type": "bouncy"})]
    keys = M.keys_for("offsetY", 0.2, segs, 4.0)
    assert len(keys) > 10
    assert keys[0]["value"] == pytest.approx(0.3)
    assert keys[-1]["value"] == pytest.approx(0.2)
    assert min(k["value"] for k in keys) < 0.2  # it bounced past
    assert all("ease" not in k for k in keys)


def test_opacity_never_overshoots():
    segs = [M.Seg("opacity", 0, 1, 0.0, 1.0, {"type": "ease-out-back"})]
    keys = M.keys_for("opacity", 1.0, segs, 2.0)
    assert all(0 <= k["value"] <= 1 for k in keys)
    assert all("ease" not in k for k in keys)  # sampled, clamped


def test_a_pan_and_a_push_on_the_same_picture_add_up():
    _scale, pan = M.camera("pan-left", 10, 0.0, 8.0, {"type": "linear"})
    a_push, _b = M.transition("push", "right", {"type": "linear"}, 4.0, 1.0)
    keys = M.keys_for("offsetX", 0.0, pan + a_push, 8.0)
    # halfway through the pan (0) and halfway through the push (-0.5)
    mid = M.value_at("offsetX", 0.0, pan + a_push, 4.5)
    assert mid == pytest.approx(0.05 - 0.1 * 4.5 / 8 - 0.5, abs=1e-6)
    assert keys[-1]["value"] == pytest.approx(-0.05 - 1.0)


def test_move_in_starts_just_outside_the_frame():
    segs = M.enter("move-in", "bottom", {"type": "ease-out"}, 0, 0.6, (0.3, 0.1), (0.0, 0.3))
    oy = [s for s in segs if s.prop == "offsetY"][0]
    assert 0.3 + oy.v0 - 0.05 >= 0.5  # the piece's top edge is below the frame
    assert not [s for s in segs if s.prop == "opacity"]  # fully there while it moves


def test_pop_starts_small_and_scale_never_goes_below_concats_limit():
    segs = M.enter("pop", "bottom", {"type": "bouncy"}, 0, 1.0, (0.1, 0.1), (0, 0))
    keys = M.keys_for("scale", 0.08, segs, 3.0)
    assert keys[0]["value"] == pytest.approx(0.05)
    assert max(k["value"] for k in keys) > 0.08  # the bounce


# -- motion from statics ------------------------------------------------------------------


@pytest.fixture()
def job(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    reg = load_registry(DEFAULTS)
    j = job_mod.create_job(jobs, reg, "Black November",
                           ["ig-story", "mall-screen-paradise-led-column", "led-screen-2"])
    root = jobs / j["id"]
    for d in j["deliverables"]:
        if d["type"] in ("png",):
            fmt = next(f for f in j["formats"] if f["id"] == d["format_id"])
            sub = {"social": "social", "screen": "led"}[fmt["kind"]]
            Image.new("RGB", (fmt["size"]["w"], fmt["size"]["h"])).save(
                root / "04_export" / sub / f"{d['expected_stem']}.png")
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (600, 200), (255, 255, 255, 255)).save(logo)
    return jobs, j["id"], logo


def _fmt(jobs, job_id, fid):
    j = job_mod.load_job(jobs, job_id)
    return j, next(f for f in j["formats"] if f["id"] == fid)


def test_defaults_are_a_gentle_push_in_with_a_dissolve(job):
    jobs, job_id, _ = job
    j, story = _fmt(jobs, job_id, "ig-story")
    plan = recipes.motion_plan(j, story, jobs / job_id)
    base, open_, close = plan.layers[0], plan.layers[-2], plan.layers[-1]
    assert plan.duration == 8.0 and (plan.width, plan.height) == (1080, 1920)
    # fades to and from black are a black still on top (Concat's clip fades don't darken)
    assert open_.file.endswith("_black_1080x1920.png") and open_.file == close.file
    assert (open_.start, open_.duration) == (0, recipes.OPEN_S)
    assert [k["value"] for k in open_.keys] == [1.0, 0.0]
    assert close.start == pytest.approx(8 - recipes.END_S)
    assert [k["value"] for k in close.keys] == [0.0, 1.0]
    assert [k["value"] for k in base.keys] == [1.0, 1.06]
    assert base.keys[-1]["ease"] == M.CURVES["ease-in-out"]


def test_older_recipe_lists_mean_the_same_choices(job):
    jobs, job_id, _ = job
    job_mod.update_job(jobs, job_id, lambda j: j.setdefault("video", {}).__setitem__(
        "motion", {"recipes": ["loop"], "length_s": 6}))
    j, story = _fmt(jobs, job_id, "ig-story")
    s = recipes.motion_settings(j, story)
    assert s["camera"]["move"] == "none" and s["ending"] == "loop" and not s["use_pieces"]
    assert s["length_s"] == 6
    # saving new settings keeps what the old list meant
    service.set_motion(jobs, job_id, {"feel": "bouncy"})
    j, story = _fmt(jobs, job_id, "ig-story")
    s = recipes.motion_settings(j, story)
    assert s["ending"] == "loop" and s["feel"] == {"type": "bouncy"}
    assert "recipes" not in j["video"]["motion"]


def test_paradise_gets_at_most_ten_seconds(job):
    jobs, job_id, _ = job
    service.set_motion(jobs, job_id, {"length_s": 15})
    j, col = _fmt(jobs, job_id, "mall-screen-paradise-led-column")
    assert recipes.motion_plan(j, col, jobs / job_id).duration == 10


def test_loop_ends_on_exactly_the_first_frame(job):
    jobs, job_id, _ = job
    service.set_motion(jobs, job_id, {"ending": "loop", "camera": {"move": "pan-up",
                                                                  "amount": 10}})
    j, story = _fmt(jobs, job_id, "ig-story")
    plan = recipes.motion_plan(j, story, jobs / job_id)
    base, tail = plan.layers[0], plan.layers[-1]
    assert not [x for x in plan.layers if "_black_" in x.file]  # a loop never goes black
    assert tail.start == pytest.approx(8 - recipes.END_S)
    assert tail.offset_y == pytest.approx(base.keys[0]["value"])  # pan's first position
    assert tail.scale == base.scale == pytest.approx(1.1)
    assert [k["value"] for k in tail.keys if k["property"] == "opacity"][-1] == 1.0


def test_second_picture_pushes_the_first_out(job, tmp_path):
    jobs, job_id, _ = job
    b = jobs / job_id / "02_assets" / "b.png"
    Image.new("RGB", (1080, 1920), "red").save(b)
    service.set_picture(jobs, job_id, "ig-story", "b", "02_assets/b.png")
    service.set_motion(jobs, job_id, {"camera": {"move": "none"}, "feel": "ease-in-out",
                                      "second": {"type": "push", "direction": "right",
                                                 "at": 3, "duration": 1}})
    j, story = _fmt(jobs, job_id, "ig-story")
    a, bl = recipes.motion_plan(j, story, jobs / job_id).layers[:2]
    assert bl.start == 3 and bl.file.endswith("b.png")
    assert [k["value"] for k in bl.keys if k["property"] == "offsetX"] == [1.0, 0.0]
    assert [k["value"] for k in a.keys if k["property"] == "offsetX"] == [0.0, -1.0]
    assert [k["at"] for k in a.keys] == [0.375, 0.5]


def test_her_own_picture_replaces_the_export(job):
    jobs, job_id, _ = job
    clean = jobs / job_id / "02_assets" / "clean.png"
    Image.new("RGB", (1080, 1920)).save(clean)
    service.set_picture(jobs, job_id, "ig-story", "a", "02_assets/clean.png")
    j, story = _fmt(jobs, job_id, "ig-story")
    assert recipes.static_for(j, story, jobs / job_id) == clean
    service.set_picture(jobs, job_id, "ig-story", "a", None)
    j, story = _fmt(jobs, job_id, "ig-story")
    assert recipes.static_for(j, story, jobs / job_id).parent.name == "social"


def test_pieces_come_in_after_the_opening_with_the_feel(job):
    jobs, job_id, logo = job
    service.add_piece(jobs, job_id, logo, "Logo")
    service.add_piece(jobs, job_id, logo, "Logo 2")
    service.set_motion(jobs, job_id, {"feel": "bouncy"})
    service.update_piece(jobs, job_id, "p2", {"enter": {"effect": "pop", "easing": "quick"}})
    j, story = _fmt(jobs, job_id, "ig-story")
    plan = recipes.motion_plan(j, story, jobs / job_id)
    p1, p2 = plan.layers[1:3]
    assert p1.start == pytest.approx(recipes.OPEN_S + 0.4)
    assert p2.start == pytest.approx(p1.start + recipes.STAGGER_S)
    assert len([k for k in p1.keys if k["property"] == "offsetY"]) > 5  # bouncy: sampled
    assert {k["property"] for k in p2.keys} == {"opacity", "scale"}


def test_piece_exit_and_hidden_on_one_size(job):
    jobs, job_id, logo = job
    service.add_piece(jobs, job_id, logo, "Logo")
    service.update_piece(jobs, job_id, "p1", {"exit": {"effect": "move-out",
                                                       "direction": "top", "at": 6}})
    service.update_piece(jobs, job_id, "p1", {"hidden": True}, format_id="led-screen-2")
    j, story = _fmt(jobs, job_id, "ig-story")
    layer = recipes.piece_layers(j, story, jobs / job_id, 8, "motion")[0]
    ys = [k for k in layer.keys if k["property"] == "offsetY"]
    assert ys[-1]["value"] < -0.5  # gone out of the top
    _j, led = _fmt(jobs, job_id, "led-screen-2")
    assert recipes.piece_layers(j, led, jobs / job_id, 8, "motion") == []


def test_piece_settings_are_checked(job):
    jobs, job_id, logo = job
    service.add_piece(jobs, job_id, logo, "Logo")
    for bad in ({"enter": {"effect": "explode"}}, {"enter": {"direction": "up"}},
                {"enter": {"easing": {"type": "spring", "stiffness": 0}}},
                {"exit": {"effect": "dissolve", "at": 99}}, {"margin_pct": 80}):
        with pytest.raises(service.VideoError):
            service.update_piece(jobs, job_id, "p1", bad)


def test_motion_settings_are_checked(job):
    jobs, job_id, _ = job
    for bad in ({"camera": {"move": "spin"}}, {"camera": {"move": "push-in", "amount": 90}},
                {"ending": "explode"}, {"second": {"type": "cube"}}, {"length_s": 0},
                {"colour": "red"}, {"feel": "wobbly"}):
        with pytest.raises(service.VideoError):
            service.set_motion(jobs, job_id, bad)


def test_one_size_can_have_its_own_motion_and_reset_it(job):
    jobs, job_id, _ = job
    service.set_motion(jobs, job_id, {"camera": {"move": "pan-left"}}, format_id="led-screen-2")
    j, led = _fmt(jobs, job_id, "led-screen-2")
    _j, story = _fmt(jobs, job_id, "ig-story")
    assert recipes.motion_settings(j, led)["camera"] == {"move": "pan-left", "amount": 6}
    assert recipes.motion_settings(j, story)["camera"]["move"] == "push-in"
    service.set_motion(jobs, job_id, format_id="led-screen-2", reset=True)
    j, led = _fmt(jobs, job_id, "led-screen-2")
    assert recipes.motion_settings(j, led)["camera"]["move"] == "push-in"


# -- the job's video sizes -------------------------------------------------------------------


def test_a_size_without_video_can_get_one_and_lose_it_again(job):
    jobs, job_id, _ = job
    j = job_mod.load_job(jobs, job_id)
    assert [c["format_id"] for c in service.video_candidates(j)] == ["led-screen-2"]
    j = service.enable_video(jobs, job_id, ["led-screen-2"])
    png = next(d for d in j["deliverables"] if d["format_id"] == "led-screen-2")
    mp4 = [d for d in j["deliverables"] if d["format_id"] == "led-screen-2" and d["type"] == "mp4"]
    assert len(mp4) == 1 and mp4[0]["expected_stem"] == png["expected_stem"]
    assert service.video_candidates(j) == []
    with pytest.raises(service.VideoError):
        service.disable_video(jobs, job_id, "ig-story")  # its video comes from the format
    j = service.disable_video(jobs, job_id, "led-screen-2")
    assert not [d for d in j["deliverables"] if d["type"] == "mp4"
                and d["format_id"] == "led-screen-2"]
    with pytest.raises(service.VideoError):
        service.enable_video(jobs, job_id, ["a4"])


def test_choosing_statics_switches_every_size(job):
    jobs, job_id, _ = job
    service.set_screen(jobs, job_id, "ig-story", mode="fit")
    j = service.set_source(jobs, job_id, "motion")
    assert all(r["mode"] == "motion" for r in service.overview(j))
    with pytest.raises(service.VideoError):
        service.set_source(jobs, job_id, "magic")


def test_preview_is_the_same_layers_concat_gets(job):
    jobs, job_id, logo = job
    service.add_piece(jobs, job_id, logo, "Logo")
    p = service.preview(jobs, job_id, "ig-story")
    assert (p["w"], p["h"], p["duration"]) == (1080, 1920, 8.0)
    assert p["layers"][0]["file"].startswith("04_export/social/")
    assert p["layers"][0]["kind"] == "image" and p["layers"][0]["w"] == 1080
    assert p["layers"][1]["file"] == "02_assets/pieces/logo.png"
    assert p["layers"][1]["keys"]
    with pytest.raises(service.VideoError):
        service.preview(jobs, job_id, "a4")
