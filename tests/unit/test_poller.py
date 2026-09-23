import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry
from studio_helper.poller import Poller

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


def _make_registry(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY_YAML, encoding="utf-8")
    return load_registry(path)


def _create_job(jobs_root, registry, now=None):
    return job_mod.create_job(jobs_root, registry, "Autumn Sale", ["ig-post"], now=now)


def _export_path(jobs_root, job) -> Path:
    stem = job["deliverables"][0]["expected_stem"]
    return jobs_root / job["id"] / "04_export" / "social" / f"{stem}.png"


def test_file_not_validated_before_two_stable_scans(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    job = _create_job(jobs_root, registry)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()
    assert poller.results_for(job["id"]) == {}


def test_file_validated_after_two_stable_scans(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    job = _create_job(jobs_root, registry)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()
    poller.scan_once()

    results = poller.results_for(job["id"])
    assert len(results) == 1
    (result,) = results.values()
    assert result.status == "ok"


def test_growing_file_resets_stability(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    job = _create_job(jobs_root, registry)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()  # size N, scan 1
    # Simulate the export still being written: size changes.
    with open(dest, "ab") as f:
        f.write(b"\x00" * 100)
    poller.scan_once()  # size changed -> stability resets
    assert poller.results_for(job["id"]) == {}

    poller.scan_once()  # size unchanged since last scan -> now stable
    assert len(poller.results_for(job["id"])) == 1


def test_revalidates_on_content_change_without_size_change(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    job = _create_job(jobs_root, registry)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()
    poller.scan_once()
    first_result = next(iter(poller.results_for(job["id"]).values()))

    # Same bytes, same size -- only the mtime changes (e.g. she
    # re-saved from the app without changing anything). Re-validation
    # is triggered by the mtime alone, per SPEC.md §6.7.
    time.sleep(0.01)
    os.utime(dest, None)
    poller.scan_once()

    second_result = next(iter(poller.results_for(job["id"]).values()))
    assert second_result is not first_result


def test_writes_report_html(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    job = _create_job(jobs_root, registry)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()
    poller.scan_once()

    report = jobs_root / job["id"] / "report.html"
    assert report.exists()
    assert "Autumn Sale" in report.read_text(encoding="utf-8")


def test_ignores_jobs_older_than_the_window(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    old_now = datetime.now(UTC).astimezone() - timedelta(days=30)
    job = _create_job(jobs_root, registry, now=old_now)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()
    poller.scan_once()

    assert poller.results_for(job["id"]) == {}


def test_removes_results_for_deleted_files(tmp_path):
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    registry = _make_registry(tmp_path)
    job = _create_job(jobs_root, registry)

    dest = _export_path(jobs_root, job)
    Image.new("RGB", (20, 20), "red").save(dest)

    poller = Poller(jobs_root)
    poller.scan_once()
    poller.scan_once()
    assert len(poller.results_for(job["id"])) == 1

    dest.unlink()
    poller.scan_once()
    assert poller.results_for(job["id"]) == {}
