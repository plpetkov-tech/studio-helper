"""End-to-end over real HTTP: the task-polling flow for Illustrator
actions and the Setup check (SPEC.md §6.2, §6.3, §5.3), with the
Adobe bridge itself mocked out since no real Illustrator is available
here."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from studio_helper.api import handlers, setup_check
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.server import create_server

REGISTRY_YAML = """\
version: 1
print_defaults:
  bleed_mm: 3
formats:
  - id: flyer-a5
    name: A5 flyer
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]
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


def test_create_print_doc_success_records_files(api, monkeypatch, tmp_path):
    call, poll = api

    def fake_create_print_doc(job, output_dir):
        ai_path = str(output_dir / f"{job['id']}_print_v01.ai")
        return {
            "ok": True,
            "data": {"documents": [{"path": ai_path, "bleed_mm": 3, "artboards": []}]},
            "errors": [],
            "warnings": [],
        }

    monkeypatch.setattr(handlers.illustrator, "create_print_doc", fake_create_print_doc)

    _status, created = call(
        "POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]}
    )
    job_id = created["job"]["id"]

    status, data = call("POST", f"/api/jobs/{job_id}/illustrator/new-print-doc")
    assert status == 200
    task_id = data["task_id"]

    result = poll(task_id)
    assert result["status"] == "done"
    assert result["result"]["ok"] is True

    _status, job_data = call("GET", f"/api/jobs/{job_id}")
    assert job_data["job"]["files"]["print"] == [f"03_working/{job_id}_print_v01.ai"]


def test_create_print_doc_bridge_failure_surfaces_as_task_error(api, monkeypatch):
    call, poll = api

    def fake_create_print_doc(job, output_dir):
        from studio_helper.adobe.bridge import AdobeBridgeError

        raise AdobeBridgeError("Illustrator did not start within 120s.")

    monkeypatch.setattr(handlers.illustrator, "create_print_doc", fake_create_print_doc)

    _status, created = call(
        "POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]}
    )
    job_id = created["job"]["id"]

    _status, data = call("POST", f"/api/jobs/{job_id}/illustrator/new-print-doc")
    result = poll(data["task_id"])
    assert result["status"] == "error"
    assert "did not start" in result["error"]


def test_unknown_task_id_is_404(api):
    call, _poll = api
    status, data = call("GET", "/api/tasks/does-not-exist")
    assert status == 404
    assert data["ok"] is False


def test_setup_check_flow(api, monkeypatch):
    call, poll = api

    monkeypatch.setattr(
        setup_check.illustrator, "inspect", lambda ai_path=None: {"data": {"pdf_presets": []}}
    )

    status, data = call("POST", "/api/setup-check")
    assert status == 200
    result = poll(data["task_id"])
    assert result["status"] == "done"
    ids = {c["id"] for c in result["result"]["checks"]}
    assert ids == {"registry", "jobs_folder", "illustrator", "pdf_preset", "mark_of_the_web"}


def test_open_scripts_folder_does_not_error(api, monkeypatch):
    monkeypatch.setattr(handlers, "open_path", lambda path, reveal: None)
    call, _poll = api
    status, data = call("POST", "/api/adobe/open-scripts-folder")
    assert status == 200
    assert data["ok"] is True


def test_setup_check_open_figma_folder_does_not_error(api, monkeypatch):
    # Must not actually launch a real file manager from a test --
    # caught for real here: xdg-open hung in this sandbox the first
    # time this test ran without the mock, timing out the request.
    monkeypatch.setattr(setup_check, "open_path", lambda path, reveal: None)
    call, _poll = api
    status, data = call("POST", "/api/setup-check/open-figma-folder")
    assert status == 200
    assert data["ok"] is True
