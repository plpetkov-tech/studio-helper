"""The Job page gets real pass/warn/fail statuses once the poller has
scanned, not just "found/missing" (SPEC.md M2)."""

import json
import threading
import urllib.error
import urllib.request

import pytest
from PIL import Image
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.poller import Poller
from studio_helper.server import create_server

REGISTRY_YAML = """\
version: 1
formats:
  - id: ig-post
    name: Instagram post
    kind: social
    size: {w: 20, h: 20, unit: px}
    exports: [png]
    allow_alpha: false
"""


@pytest.fixture()
def api_with_poller(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(REGISTRY_YAML, encoding="utf-8")

    poller = Poller(jobs_root)
    cfg = Config(jobs_root=str(jobs_root), registry_path=str(registry_path))
    ctx = AppContext(cfg, poller=poller)
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

    yield call, jobs_root, poller

    server.shutdown()
    server.server_close()


def test_job_deliverable_reflects_real_validation(api_with_poller):
    call, jobs_root, poller = api_with_poller

    _status, created = call("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["ig-post"]})
    job = created["job"]
    stem = job["deliverables"][0]["expected_stem"]
    export_path = jobs_root / job["id"] / "04_export" / "social" / f"{stem}.png"
    Image.new("RGB", (20, 20), "red").save(export_path)

    # Before the poller has scanned: still "missing" via the live path
    # (no naive fallback once a poller is attached).
    status, data = call("GET", f"/api/jobs/{job['id']}")
    assert data["deliverables"][0]["status"] == "missing"

    poller.scan_once()
    poller.scan_once()

    status, data = call("GET", f"/api/jobs/{job['id']}")
    assert data["deliverables"][0]["status"] == "ok"
    assert data["deliverables"][0]["found_file"] == f"{stem}.png"
    assert data["deliverables"][0]["checks"]


def test_home_progress_counts_validated_deliverables(api_with_poller):
    call, jobs_root, poller = api_with_poller

    _status, created = call("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["ig-post"]})
    job = created["job"]
    stem = job["deliverables"][0]["expected_stem"]
    export_path = jobs_root / job["id"] / "04_export" / "social" / f"{stem}.png"
    Image.new("RGB", (20, 20), "red").save(export_path)

    poller.scan_once()
    poller.scan_once()

    status, data = call("GET", "/api/jobs")
    assert data["jobs"][0]["deliverables_done"] == 1
    assert data["jobs"][0]["deliverables_total"] == 1
