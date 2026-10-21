"""One master, cut to every size, over real HTTP, with Illustrator and
Photoshop mocked: choose the way, make the master, its picture, the box,
the cut into 04_export and into the print file."""

import time
from pathlib import Path

from PIL import Image, ImageDraw
from studio_helper.api import master_routes
from test_video_api import api  # noqa: F401 - the server fixture


def _wait(jcall, task_id):
    for _ in range(100):
        _s, task = jcall("GET", f"/api/tasks/{task_id}")
        if task["status"] != "running":
            return task
        time.sleep(0.05)
    raise AssertionError("the task never finished")


def _png(path: Path, w=3000, h=2250) -> bytes:
    im = Image.new("RGB", (w, h), (16, 22, 48))
    ImageDraw.Draw(im).rectangle([w * 0.4, h * 0.4, w * 0.6, h * 0.6], fill=(255, 196, 0))
    im.save(path)
    return path.read_bytes()


def test_a_photoshop_master_cut_into_every_digital_size(api, tmp_path, monkeypatch):  # noqa: F811
    call, jcall, _token, jobs = api
    _s, data = jcall("POST", "/api/jobs", {"name": "Master", "format_ids": ["ig-story", "ig-post",
                                                                            "flyer-a4"]})
    job_id = data["job"]["id"]
    _s, v = jcall("GET", f"/api/jobs/{job_id}/master")
    m = v["master"]
    assert m["mode"] is None and m["app"] == "ai" and len(m["sizes"]) == 3

    _s, v = jcall("POST", f"/api/jobs/{job_id}/master", {"mode": "master", "app": "ps"})
    m = v["master"]
    assert m["mode"] == "master" and [s["format_id"] for s in m["sizes"]] == ["ig-story", "ig-post"]
    assert m["left_out"] == [{"format_id": "flyer-a4", "name": m["left_out"][0]["name"],
                              "kind": "print", "why": "print"}]
    assert m["plan"]["unit"] == "px" and m["plan"]["w"] >= 1080

    made = {}

    def fake_make(path, w, h):
        made.update(path=path, w=w, h=h)
        return {"ok": True, "data": {"path": str(path), "existed": False}, "errors": [],
                "warnings": []}

    monkeypatch.setattr(master_routes.photoshop, "make_master", fake_make)
    _s, data = jcall("POST", f"/api/jobs/{job_id}/master/make")
    assert _wait(jcall, data["task_id"])["status"] == "done"
    assert made["path"].name == f"{job_id}_master_v01.psd" and made["w"] == m["plan"]["w"]
    _s, v = jcall("GET", f"/api/jobs/{job_id}/master")
    assert v["master"]["file"] == f"03_working/{job_id}_master_v01.psd"
    status, v = jcall("POST", f"/api/jobs/{job_id}/master", {"app": "ai"})
    assert status == 400  # the master is made: no switching apps under her

    status, data = jcall("POST", f"/api/jobs/{job_id}/master/cut")
    assert status == 400 and "Read the master" in data["error"]

    def fake_export(path, out):
        _png(out)
        return {"ok": True, "data": {"out": str(out)}, "errors": [], "warnings": []}

    monkeypatch.setattr(master_routes.photoshop, "export_master", fake_export)
    _s, data = jcall("POST", f"/api/jobs/{job_id}/master/read")
    assert _wait(jcall, data["task_id"])["status"] == "done"
    _s, v = jcall("GET", f"/api/jobs/{job_id}/master")
    m = v["master"]
    assert m["preview"] == "02_assets/master/master.png" and (m["pw"], m["ph"]) == (3000, 2250)
    status, _b, _h = call("GET", f"/api/jobs/{job_id}/file?rel={m['small']}&t={_token}",
                          token=False)
    assert status == 200  # the page can show it

    _s, v = jcall("POST", f"/api/jobs/{job_id}/master", {"box": [0.38, 0.38, 0.24, 0.24]})
    _s, v = jcall("POST", f"/api/jobs/{job_id}/master",
                  {"box": [0.1, 0.1, 0.3, 0.3], "format_id": "ig-post"})
    assert next(s for s in v["master"]["sizes"] if s["format_id"] == "ig-post")["own"]
    _s, v = jcall("POST", f"/api/jobs/{job_id}/master", {"format_id": "ig-post", "reset": True})
    _s, v = jcall("POST", f"/api/jobs/{job_id}/master", {"fill": "color", "brand_color": "#ff0000"})
    assert v["master"]["fill"] == "color"
    status, _d = jcall("POST", f"/api/jobs/{job_id}/master", {"fill": "sparkles"})
    assert status == 400

    _s, data = jcall("POST", f"/api/jobs/{job_id}/master/cut")
    task = _wait(jcall, data["task_id"])
    assert task["status"] == "done" and task["result"]["ok"], task
    assert {x["format_id"] for x in task["result"]["data"]["made"]} == {"ig-story", "ig-post"}
    root = jobs / job_id
    for x in task["result"]["data"]["made"]:
        assert (root / x["file"]).is_file()
    _s, v = jcall("GET", f"/api/jobs/{job_id}/master")
    assert all(s["cut"] and not s["theirs"] for s in v["master"]["sizes"])

    # a picture she exported herself, dropped in instead
    status, body, _h = call("POST", f"/api/jobs/{job_id}/upload?to=master&name=mine.png",
                            raw=_png(tmp_path / "mine.png", 2000, 1500))
    assert status == 200
    _s, v = jcall("GET", f"/api/jobs/{job_id}/master")
    assert (v["master"]["pw"], v["master"]["ph"]) == (2000, 1500)


def test_an_illustrator_master_places_print_in_the_print_file(api, monkeypatch):  # noqa: F811
    _call, jcall, _token, jobs = api
    _s, data = jcall("POST", "/api/jobs", {"name": "Print", "format_ids": ["flyer-a4"]})
    job_id = data["job"]["id"]
    jcall("POST", f"/api/jobs/{job_id}/master", {"mode": "master", "app": "ai"})
    seen = {}

    monkeypatch.setattr(master_routes.illustrator, "make_master", lambda path, w, h, cmyk: (
        seen.update(cmyk=cmyk) or {"ok": True, "data": {"path": str(path)}}))
    _s, data = jcall("POST", f"/api/jobs/{job_id}/master/make")
    assert _wait(jcall, data["task_id"])["status"] == "done" and seen["cmyk"]

    def fake_create(job, output_dir):
        p = output_dir / f"{job['id']}_print_v01.ai"
        p.write_text("ai")
        return {"ok": True, "data": {"documents": [{"path": str(p)}]}}

    def fake_cut(master_path, ai_paths, cuts, fill, brand_color):
        seen.update(master=master_path, ai_paths=ai_paths, cuts=cuts)
        return {"ok": True, "data": {"cut": [{"format_id": "flyer-a4", "file": str(ai_paths[0])}]},
                "errors": [], "warnings": []}

    monkeypatch.setattr(master_routes.illustrator, "create_print_doc", fake_create)
    monkeypatch.setattr(master_routes.illustrator, "cut_master", fake_cut)
    _s, data = jcall("POST", f"/api/jobs/{job_id}/master/cut")  # no picture needed for print
    task = _wait(jcall, data["task_id"])
    assert task["status"] == "done" and task["result"]["ok"], task
    assert seen["master"].name == f"{job_id}_master_v01.ai"
    assert [p.name for p in seen["ai_paths"]] == [f"{job_id}_print_v01.ai"]  # made for her first
    assert seen["cuts"][0]["format_id"] == "flyer-a4" and seen["cuts"][0]["bleed_mm"] == 3
    _s, v = jcall("GET", f"/api/jobs/{job_id}/master")
    assert v["master"]["has_print_file"] and v["master"]["sizes"][0]["cut"]
