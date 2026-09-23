"""End-to-end over real HTTP: the task-polling flow for Photoshop
actions (SPEC.md §6.2, §6.3, §6.5), with the Adobe bridge itself
mocked out since no real Photoshop is available here."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from studio_helper.api import handlers
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.server import create_server

REGISTRY_YAML = """\
version: 1
formats:
  - id: ig-post
    name: Instagram post
    kind: social
    size: {w: 1080, h: 1350, unit: px}
    exports: [png]
    allow_alpha: false
  - id: led-mall-entrance
    name: LED mall entrance
    kind: screen
    size: {w: 384, h: 1920, unit: px}
    exports: [png]
    allow_alpha: false
"""


@pytest.fixture()
def api(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(REGISTRY_YAML, encoding="utf-8")

    ctx = AppContext(Config(jobs_root=str(jobs_root), registry_path=str(registry_path)))
    server = create_server(ctx=ctx)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def call(method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=data,
            method=method,
            headers={
                "Host": f"127.0.0.1:{port}",
                "X-Studio-Helper-Token": server.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def poll(task_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _status, data = call("GET", f"/api/tasks/{task_id}")
            if data["status"] != "running":
                return data
            time.sleep(0.02)
        raise AssertionError("task did not finish in time")

    yield call, poll

    server.shutdown()
    server.server_close()


def test_create_digital_doc_success_records_psd(api, monkeypatch, tmp_path):
    call, poll = api

    def fake_create_digital_doc(job, output_dir):
        psd_path = str(output_dir / f"{job['id']}_digital_v01.psd")
        return {
            "ok": True,
            "data": {"path": psd_path, "artboards": []},
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(handlers.photoshop, "create_digital_doc", fake_create_digital_doc)

    _status, created = call(
        "POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["ig-post", "led-mall-entrance"]}
    )
    job_id = created["job"]["id"]

    status, data = call("POST", f"/api/jobs/{job_id}/photoshop/new-digital-doc")
    assert status == 200
    result = poll(data["task_id"])
    assert result["status"] == "done"
    assert result["result"]["ok"] is True

    _status, job_data = call("GET", f"/api/jobs/{job_id}")
    assert job_data["job"]["files"]["psd"] == f"03_working/{job_id}_digital_v01.psd"


def test_create_digital_doc_bridge_failure_surfaces_as_task_error(api, monkeypatch):
    call, poll = api

    def fake_create_digital_doc(job, output_dir):
        from studio_helper.adobe.bridge import AdobeBridgeError

        raise AdobeBridgeError("Photoshop did not start within 120s.")

    monkeypatch.setattr(handlers.photoshop, "create_digital_doc", fake_create_digital_doc)

    _status, created = call(
        "POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["ig-post"]}
    )
    job_id = created["job"]["id"]

    _status, data = call("POST", f"/api/jobs/{job_id}/photoshop/new-digital-doc")
    result = poll(data["task_id"])
    assert result["status"] == "error"
    assert "did not start" in result["error"]


def test_export_digital_with_no_psd_is_400(api):
    call, _poll = api
    _status, created = call(
        "POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["ig-post"]}
    )
    job_id = created["job"]["id"]
    status, data = call("POST", f"/api/jobs/{job_id}/photoshop/export-digital")
    assert status == 400
    assert "Create Photoshop file" in data["error"]


def test_export_digital_passes_per_kind_export_dirs(api, monkeypatch, tmp_path):
    call, poll = api

    def fake_create_digital_doc(job, output_dir):
        psd_path = str(output_dir / f"{job['id']}_digital_v01.psd")
        return {"ok": True, "data": {"path": psd_path, "artboards": []}}

    captured = {}

    def fake_export_digital(job, psd_path, export_dirs):
        captured["psd_path"] = psd_path
        captured["export_dirs"] = export_dirs
        return {"ok": True, "data": {"exported": [{"path": "x.png", "type": "png"}]}}

    monkeypatch.setattr(handlers.photoshop, "create_digital_doc", fake_create_digital_doc)
    monkeypatch.setattr(handlers.photoshop, "export_digital", fake_export_digital)

    _status, created = call(
        "POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["ig-post", "led-mall-entrance"]}
    )
    job_id = created["job"]["id"]

    _status, data = call("POST", f"/api/jobs/{job_id}/photoshop/new-digital-doc")
    poll(data["task_id"])

    status, data = call("POST", f"/api/jobs/{job_id}/photoshop/export-digital")
    assert status == 200
    result = poll(data["task_id"])
    assert result["result"]["data"]["exported"] == [{"path": "x.png", "type": "png"}]

    assert set(captured["export_dirs"].keys()) == {"social", "screen"}
    assert captured["export_dirs"]["social"].name == "social"
    assert captured["export_dirs"]["screen"].name == "led"
    assert captured["psd_path"].name == f"{job_id}_digital_v01.psd"
