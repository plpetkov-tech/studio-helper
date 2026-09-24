"""End-to-end over real HTTP for /api/update/* (SPEC.md §15,
2026-09-24), with updater.py's network calls mocked out -- these tests
must never touch the real network."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
from studio_helper import updater
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.server import create_server

REGISTRY_YAML = """\
version: 1
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


def _fake_info(available, **overrides):
    defaults = dict(
        current_version="0.1.0",
        latest_version="9.9.9",
        available=available,
        notes="Notes.",
        html_url="https://x",
        zip_url="https://x/zip",
        zip_name="StudioHelper-v9.9.9.zip",
        sha256sums_url="https://x/sums",
    )
    defaults.update(overrides)
    return updater.UpdateInfo(**defaults)


def test_update_check_reports_available(api, monkeypatch):
    call, poll = api
    monkeypatch.setattr(updater, "check_for_update", lambda: _fake_info(True))

    status, data = call("POST", "/api/update/check")
    assert status == 200
    result = poll(data["task_id"])
    assert result["status"] == "done"
    assert result["result"]["available"] is True
    assert result["result"]["latest_version"] == "9.9.9"


def test_update_check_reports_up_to_date(api, monkeypatch):
    call, poll = api
    monkeypatch.setattr(updater, "check_for_update", lambda: _fake_info(False))

    status, data = call("POST", "/api/update/check")
    result = poll(data["task_id"])
    assert result["result"]["available"] is False


def test_update_check_network_failure_surfaces_as_task_error(api, monkeypatch):
    call, poll = api

    def boom():
        raise updater.UpdateError("Could not reach GitHub: no route to host")

    monkeypatch.setattr(updater, "check_for_update", boom)

    status, data = call("POST", "/api/update/check")
    result = poll(data["task_id"])
    assert result["status"] == "error"
    assert "Could not reach GitHub" in result["error"]


def test_update_install_downloads_and_schedules_relaunch(api, monkeypatch, tmp_path):
    call, poll = api
    monkeypatch.setattr(updater, "check_for_update", lambda: _fake_info(True))

    staged = tmp_path / "StudioHelper-v9.9.9"
    staged.mkdir()
    captured = {}
    monkeypatch.setattr(updater, "download_and_stage", lambda info: staged)
    monkeypatch.setattr(
        updater, "schedule_relaunch", lambda new_dir: captured.setdefault("new_dir", new_dir)
    )

    status, data = call("POST", "/api/update/install")
    assert status == 200
    result = poll(data["task_id"])
    assert result["status"] == "done"
    assert result["result"]["installed"] is True
    assert captured["new_dir"] == staged


def test_update_install_skips_when_already_current(api, monkeypatch):
    call, poll = api
    monkeypatch.setattr(updater, "check_for_update", lambda: _fake_info(False))

    called = {"download": False}

    def fail_if_called(info):
        called["download"] = True
        raise AssertionError("should not download when not available")

    monkeypatch.setattr(updater, "download_and_stage", fail_if_called)

    status, data = call("POST", "/api/update/install")
    result = poll(data["task_id"])
    assert result["result"]["installed"] is False
    assert called["download"] is False


def test_update_install_bubbles_checksum_failure(api, monkeypatch):
    call, poll = api
    monkeypatch.setattr(updater, "check_for_update", lambda: _fake_info(True))

    def fail_checksum(info):
        raise updater.UpdateError("Downloaded file's checksum doesn't match the release")

    monkeypatch.setattr(updater, "download_and_stage", fail_checksum)

    status, data = call("POST", "/api/update/install")
    result = poll(data["task_id"])
    assert result["status"] == "error"
    assert "checksum doesn't match" in result["error"]
