import json
import threading
import urllib.error
import urllib.request

import pytest
from studio_helper.api.context import AppContext
from studio_helper.config import Config
from studio_helper.server import create_server

REGISTRY_YAML = """\
version: 1
print_defaults:
  bleed_mm: 3
  safe_mm: 5
  pdf_preset: StudioHelper_X1a
formats:
  - id: flyer-a5
    name: A5 flyer
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]
  - id: ig-post
    name: Instagram post
    kind: social
    size: {w: 1080, h: 1350, unit: px}
    exports: [png]
job_types:
  full-campaign: [flyer-a5, ig-post]
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

    yield call

    server.shutdown()
    server.server_close()


def test_get_registry(api):
    status, data = api("GET", "/api/registry")
    assert status == 200
    assert data["ok"] is True
    ids = {f["id"] for f in data["formats"]}
    assert ids == {"flyer-a5", "ig-post"}


def test_validate_registry_ok(api):
    status, data = api("POST", "/api/registry/validate")
    assert status == 200
    assert data["ok"] is True


def test_create_job_via_format_ids(api):
    status, data = api("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]})
    assert status == 200
    assert data["job"]["slug"] == "autumn-sale"
    assert len(data["job"]["deliverables"]) == 1


def test_create_job_via_job_type(api):
    status, data = api("POST", "/api/jobs", {"name": "Campaign", "job_type": "full-campaign"})
    assert status == 200
    format_ids = {f["id"] for f in data["job"]["formats"]}
    assert format_ids == {"flyer-a5", "ig-post"}


def test_create_job_missing_name_is_400(api):
    status, data = api("POST", "/api/jobs", {"name": "", "format_ids": ["flyer-a5"]})
    assert status == 400
    assert data["ok"] is False


def test_list_jobs_after_create(api):
    api("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]})
    status, data = api("GET", "/api/jobs")
    assert status == 200
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["deliverables_total"] == 1
    assert data["jobs"][0]["deliverables_done"] == 0


def test_get_job_by_id(api):
    _status, created = api("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]})
    job_id = created["job"]["id"]
    status, data = api("GET", f"/api/jobs/{job_id}")
    assert status == 200
    assert data["job"]["id"] == job_id
    assert data["deliverables"][0]["status"] == "missing"


def test_get_job_not_found(api):
    status, data = api("GET", "/api/jobs/does-not-exist")
    assert status == 400
    assert data["ok"] is False


def test_start_revision_bumps_version(api):
    _status, created = api("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]})
    job_id = created["job"]["id"]
    status, data = api("POST", f"/api/jobs/{job_id}/revision")
    assert status == 200
    assert data["job"]["version"] == 2


def test_deliverable_status_reflects_export_dir(api, tmp_path):
    _status, created = api("POST", "/api/jobs", {"name": "Autumn Sale", "format_ids": ["flyer-a5"]})
    job = created["job"]
    export_dir = tmp_path / "jobs" / job["id"] / "04_export" / "print"
    stem = job["deliverables"][0]["expected_stem"]
    (export_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4 fake")

    status, data = api("GET", f"/api/jobs/{job['id']}")
    assert status == 200
    assert data["deliverables"][0]["status"] == "found"
