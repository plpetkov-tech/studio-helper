"""Add sizes to an existing job, remove and restore a size (ROADMAP R2)."""

import json
import threading

import pytest
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry
from test_job import FIXED_NOW, REGISTRY_YAML

EXTRA = """\
  - id: mall-x-citylight
    name: Mall X CityLight
    kind: print
    size: {w: 1185, h: 1750, unit: mm}
    exports: [tiff]
"""


@pytest.fixture()
def registry(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY_YAML.replace("job_types:", EXTRA + "job_types:"), encoding="utf-8")
    return load_registry(path)


@pytest.fixture()
def jobs_root(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    return root


def _job(jobs_root, registry):
    return job_mod.create_job(jobs_root, registry, "Black November", ["flyer-a5", "ig-post"],
                              now=FIXED_NOW)


def test_add_sizes_joins_the_current_version_and_records_a_batch(jobs_root, registry):
    job = _job(jobs_root, registry)
    job_mod.bump_version(jobs_root, job["id"])
    job_mod.bump_version(jobs_root, job["id"])

    job = job_mod.add_formats(jobs_root, job["id"], registry, ["mall-x-citylight"])
    assert job["version"] == 3  # not a revision
    new = [d for d in job["deliverables"] if d["format_id"] == "mall-x-citylight"]
    assert [d["type"] for d in new] == ["tiff"]
    # same date and slug as the job's other files, current version
    assert new[0]["expected_stem"] == (
        "2026-09-25_black-november_mall-x-citylight_1185x1750mm_v03")
    assert job["added"][0]["batch"] == 1
    assert job["added"][0]["format_ids"] == ["mall-x-citylight"]
    assert job_mod.load_job(jobs_root, job["id"]) == job  # persisted


def test_add_sizes_refuses_duplicates_unknown_and_empty(jobs_root, registry):
    job = _job(jobs_root, registry)
    with pytest.raises(job_mod.JobError, match="Already in this job"):
        job_mod.add_formats(jobs_root, job["id"], registry, ["flyer-a5"])
    with pytest.raises(job_mod.JobError, match="Unknown"):
        job_mod.add_formats(jobs_root, job["id"], registry, ["nope"])
    with pytest.raises(job_mod.JobError, match="at least one"):
        job_mod.add_formats(jobs_root, job["id"], registry, [])


def test_bad_bleed_writes_nothing(jobs_root, registry):
    job = _job(jobs_root, registry)
    before = (jobs_root / job["id"] / "job.json").read_text()
    with pytest.raises(job_mod.JobError):
        job_mod.add_formats(jobs_root, job["id"], registry, ["mall-x-citylight"],
                            bleed_overrides={"mall-x-citylight": -2})
    assert (jobs_root / job["id"] / "job.json").read_text() == before


def test_create_job_with_bad_bleed_leaves_no_folder(jobs_root, registry):
    with pytest.raises(job_mod.JobError):
        job_mod.create_job(jobs_root, registry, "Oops", ["flyer-a5"],
                           bleed_overrides={"flyer-a5": "abc"}, now=FIXED_NOW)
    assert list(jobs_root.iterdir()) == []


def test_remove_and_restore_a_size(jobs_root, registry):
    job = _job(jobs_root, registry)
    job = job_mod.remove_format(jobs_root, job["id"], "ig-post")
    assert [f["id"] for f in job["formats"]] == ["flyer-a5"]
    assert all(d["format_id"] != "ig-post" for d in job["deliverables"])
    assert job["removed"][0]["format"]["id"] == "ig-post"

    job_mod.bump_version(jobs_root, job["id"])  # a revision while it's removed
    job = job_mod.restore_format(jobs_root, job["id"], "ig-post")
    stems = [d["expected_stem"] for d in job["deliverables"] if d["format_id"] == "ig-post"]
    assert stems == ["2026-09-25_black-november_ig-post_1080x1350px_v02"]
    assert job["removed"] == []


def test_cannot_remove_the_last_size(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "One", ["flyer-a5"], now=FIXED_NOW)
    with pytest.raises(job_mod.JobError, match="at least one size"):
        job_mod.remove_format(jobs_root, job["id"], "flyer-a5")


def test_adding_back_a_removed_size_clears_it_from_removed(jobs_root, registry):
    job = _job(jobs_root, registry)
    job_mod.remove_format(jobs_root, job["id"], "ig-post")
    job = job_mod.add_formats(jobs_root, job["id"], registry, ["ig-post"])
    assert job["removed"] == []


def test_add_on_file_takes_the_print_set_version_not_the_job_version(jobs_root, registry):
    # The trap from ROADMAP R2: she keeps working in her v01 file at job v3.
    job = _job(jobs_root, registry)
    job_mod.record_print_files(jobs_root, job["id"], ["03_working/x_print_v01.ai"])
    job_mod.bump_version(jobs_root, job["id"])
    job = job_mod.bump_version(jobs_root, job["id"])
    assert job_mod.print_set_version(job) == 1

    job = job_mod.record_print_files(jobs_root, job["id"], ["03_working/x_print_add01_v01.ai"])
    assert job_mod.current_print_files(job) == [
        "03_working/x_print_v01.ai", "03_working/x_print_add01_v01.ai"]


def test_concurrent_add_and_bump_lose_nothing(jobs_root, registry):
    job = _job(jobs_root, registry)
    barrier = threading.Barrier(2)

    def add():
        barrier.wait()
        job_mod.add_formats(jobs_root, job["id"], registry, ["mall-x-citylight"])

    def bump():
        barrier.wait()
        job_mod.bump_version(jobs_root, job["id"])

    threads = [threading.Thread(target=add), threading.Thread(target=bump)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = json.loads((jobs_root / job["id"] / "job.json").read_text())
    assert final["version"] == 2
    assert any(f["id"] == "mall-x-citylight" for f in final["formats"])
