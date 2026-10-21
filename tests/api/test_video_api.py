"""Video step over real HTTP: uploads, the video file stream (Range), the
juice box and fill switch, and rendering as a task with progress, with a
fake Concat (ROADMAP R5-R7)."""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image
from studio_helper.api import video_routes
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.server import create_server

FIX = Path(__file__).resolve().parents[1] / "fixtures"
sys.path.insert(0, str(FIX))
from mp4_fixture import make_mp4  # noqa: E402

DEFAULTS = Path(__file__).resolve().parents[2] / "defaults" / "registry.yaml"
FAKE = [sys.executable, str(FIX / "fake_concat.py")]


@pytest.fixture()
def api(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    ctx = AppContext(Config(jobs_root=str(jobs), registry_path=str(DEFAULTS)))
    server = create_server(ctx=ctx)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def call(method, path, payload=None, raw=None, headers=None, token=True):
        data = raw if raw is not None else (
            json.dumps(payload).encode() if payload is not None else None)
        h = {"Host": f"127.0.0.1:{port}"}
        if token:
            h["X-Studio-Helper-Token"] = server.token
        h["Content-Type"] = "application/octet-stream" if raw is not None else "application/json"
        h.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read()
                return resp.status, body, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def jcall(method, path, payload=None, **kw):
        status, body, _h = call(method, path, payload, **kw)
        return status, json.loads(body)

    yield call, jcall, server.token, jobs
    server.shutdown()
    server.server_close()


def test_upload_stream_juice_fill_and_render(api, tmp_path, monkeypatch):
    call, jcall, token, jobs = api
    _s, data = jcall("POST", "/api/jobs", {"name": "Video", "format_ids": ["ig-story"]})
    job_id = data["job"]["id"]

    master = make_mp4(tmp_path / "m.mp4", w=1080, h=1920, seconds=6, fps=24, padding_bytes=5000)
    status, body, _ = call("POST", f"/api/jobs/{job_id}/upload?to=video&name=hf%20master.mp4",
                           raw=master.read_bytes())
    assert status == 200, body
    masters = json.loads(body)["masters"]
    assert masters[0]["file"] == "02_assets/video/hf master.mp4"
    assert not list((jobs / job_id / ".uploads").iterdir())  # temp file cleaned up

    # the browser's video player: token in the URL, seeking with Range
    rel = "02_assets/video/hf%20master.mp4"
    status, part, headers = call("GET", f"/api/jobs/{job_id}/file?rel={rel}&t={token}",
                                 headers={"Range": "bytes=0-99"}, token=False)
    assert status == 206 and len(part) == 100 and headers["Accept-Ranges"] == "bytes"
    status, _b, _h = call("GET", f"/api/jobs/{job_id}/file?rel={rel}", token=False)
    assert status == 401
    status, _b, _h = call("GET", f"/api/jobs/{job_id}/file?rel=job.json&t={token}", token=False)
    assert status == 404  # only assets and exports

    logo = tmp_path / "logo.png"
    Image.new("RGBA", (300, 100)).save(logo)
    status, body, _ = call("POST", f"/api/jobs/{job_id}/upload?to=piece&name=logo.png",
                           raw=logo.read_bytes())
    assert status == 200 and json.loads(body)["pieces"][0]["label"] == "logo"

    status, data = jcall("POST", f"/api/jobs/{job_id}/video/juice",
                         {"master": "m1", "keys": [{"t": 0, "box": [0.2, 0.2, 0.6, 0.4]}]})
    assert status == 200 and data["masters"][0]["juice"][0]["box"] == [0.2, 0.2, 0.6, 0.4]
    status, data = jcall("POST", f"/api/jobs/{job_id}/video/fill", {"fill": "black"})
    assert data["fill"] == "black"
    status, data = jcall("POST", f"/api/jobs/{job_id}/video/fill", {"fill": "purple"})
    assert status == 400

    real = video_routes.service.render_all
    monkeypatch.setattr(video_routes.concat, "find_concat", lambda configured=None: Path("x"))
    monkeypatch.setattr(video_routes.service, "render_all",
                        lambda *a, **k: real(*a, **dict(k, concat_exe=None,
                                                        concat_command=FAKE)))
    status, data = jcall("POST", f"/api/jobs/{job_id}/video/render", {})
    assert status == 200
    for _ in range(200):
        _s, task = jcall("GET", f"/api/tasks/{data['task_id']}")
        if task["status"] != "running":
            break
        time.sleep(0.05)
    assert task["status"] == "done" and task["result"]["data"]["rendered"] == ["ig-story"], task
    _s, data = jcall("GET", f"/api/jobs/{job_id}/video")
    assert data["screens"][0]["rendered"]["mode"] == "fit"


def test_render_without_concat_says_how_to_get_it(api, monkeypatch):
    _call, jcall, _token, _jobs = api
    _s, data = jcall("POST", "/api/jobs", {"name": "Video", "format_ids": ["ig-story"]})
    monkeypatch.setattr(video_routes.concat, "find_concat", lambda configured=None: None)
    status, data = jcall("POST", f"/api/jobs/{data['job']['id']}/video/render", {})
    assert status == 400 and "Install it" in data["error"]


def test_upload_rejects_wrong_types_and_never_uses_browser_paths(api, tmp_path):
    call, _jcall, _token, jobs = api
    _s, body, _ = call("POST", "/api/jobs", {"name": "V", "format_ids": ["ig-story"]})
    job_id = json.loads(body)["job"]["id"]
    status, body, _ = call("POST", f"/api/jobs/{job_id}/upload?to=video&name=evil.exe",
                           raw=b"MZ")
    assert status == 400
    png = tmp_path / "p.png"
    Image.new("RGB", (10, 10)).save(png)
    status, body, _ = call("POST",
                           f"/api/jobs/{job_id}/upload?to=piece&name=..%2F..%2Fescape.png",
                           raw=png.read_bytes())
    assert status == 200
    assert json.loads(body)["pieces"][0]["file"] == "02_assets/pieces/escape.png"


def test_spec_sheet_is_kept_with_the_format(api, tmp_path, monkeypatch):
    call, jcall, _token, _jobs = api
    import studio_helper.paths as paths

    monkeypatch.setattr(paths, "app_data_dir", lambda: tmp_path / "appdata")
    registry = tmp_path / "registry.yaml"
    registry.write_text(DEFAULTS.read_text(encoding="utf-8"), encoding="utf-8")
    from studio_helper.api import handlers
    monkeypatch.setattr(handlers, "_load_registry",
                        lambda ctx: handlers.load_registry(registry))
    monkeypatch.setattr(handlers.registry_edit, "update_format",
                        lambda _p, fid, ch, real=handlers.registry_edit.update_format:
                        real(registry, fid, ch))
    status, body, _ = call(
        "POST", "/api/registry/formats/mall-screen-veliko-turnovo-led/spec?name=VT%20sheet.jpg",
        raw=b"\xff\xd8\xff jpeg")
    assert status == 200, body
    fmt = json.loads(body)["format"]
    assert fmt["source_file"].endswith("specs/mall-screen-veliko-turnovo-led/VT sheet.jpg")
    assert Path(fmt["source_file"]).read_bytes() == b"\xff\xd8\xff jpeg"


def test_statics_to_video_from_the_video_tab(api, tmp_path):
    """The statics path end to end over HTTP: a size gets a video, she
    picks "from statics", chooses a picture, sets Figma-style motion,
    and the preview is the data the browser plays."""
    call, jcall, token, jobs = api
    _s, data = jcall("POST", "/api/jobs", {"name": "Statics", "format_ids": ["led-screen-2"]})
    job_id = data["job"]["id"]
    _s, v = jcall("GET", f"/api/jobs/{job_id}/video")
    assert v["screens"] == [] and v["candidates"][0]["format_id"] == "led-screen-2"
    assert v["source"] is None
    _s, v = jcall("POST", f"/api/jobs/{job_id}/video/enable", {"format_ids": ["led-screen-2"]})
    assert [s["format_id"] for s in v["screens"]] == ["led-screen-2"] and v["candidates"] == []
    assert v["screens"][0]["video_added"] and v["screens"][0]["picture"] is None

    _s, v = jcall("POST", f"/api/jobs/{job_id}/video/source", {"source": "motion"})
    assert v["source"] == "motion" and v["screens"][0]["mode"] == "motion"
    status, data = jcall("GET", f"/api/jobs/{job_id}/video/preview/led-screen-2")
    assert status == 400 and "static" in data["error"]

    pic = tmp_path / "bg.png"
    Image.new("RGB", (1280, 2400), "navy").save(pic)
    status, body, _ = call("POST", f"/api/jobs/{job_id}/upload?to=motion-a&format=led-screen-2"
                           "&name=bg.png", raw=pic.read_bytes())
    assert status == 200 and json.loads(body)["warnings"] == []
    _s, v = jcall("GET", f"/api/jobs/{job_id}/video")
    row = v["screens"][0]
    assert row["picture"] == "02_assets/motion-a/bg.png" and row["picture_own"]

    status, v = jcall("POST", f"/api/jobs/{job_id}/video/motion",
                      {"changes": {"feel": {"type": "spring", "mass": 3, "stiffness": 150,
                                            "damping": 8},
                                   "camera": {"move": "pan-up", "amount": 10}, "ending": "loop"}})
    assert status == 200 and v["motion"]["feel"]["mass"] == 3
    assert v["options"]["springs"]["gentle"]["duration_s"] > 0
    status, data = jcall("POST", f"/api/jobs/{job_id}/video/motion",
                         {"changes": {"camera": {"move": "barrel-roll"}}})
    assert status == 400

    _s, data = jcall("GET", f"/api/jobs/{job_id}/video/preview/led-screen-2")
    p = data["preview"]
    assert (p["w"], p["h"]) == (1280, 2400) and p["meta"]["ending"] == "loop"
    assert p["layers"][0]["file"] == "02_assets/motion-a/bg.png"
    status, _b, _h = call("GET", f"/api/jobs/{job_id}/file?rel={p['layers'][0]['file']}&t={token}",
                          token=False)
    assert status == 200  # the browser can fetch every layer it's given

    _s, v = jcall("POST", f"/api/jobs/{job_id}/video/picture",
                  {"format_id": "led-screen-2", "which": "a"})
    assert v["screens"][0]["picture"] is None
    _s, v = jcall("POST", f"/api/jobs/{job_id}/video/disable", {"format_id": "led-screen-2"})
    assert v["screens"] == []
