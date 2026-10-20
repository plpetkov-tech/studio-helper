import zipfile

import pytest
from studio_helper import delivery
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry
from test_job import FIXED_NOW, REGISTRY_YAML

EXTRA = """\
  - id: mall-x-door
    name: Mall X door
    group: Mall print
    notes: "Print shop: 5 mm bleed."
    kind: print
    size: {w: 850, h: 2000, unit: mm}
    exports: [tiff]
"""


@pytest.fixture()
def setup(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY_YAML.replace("job_types:", EXTRA + "job_types:"), encoding="utf-8")
    reg = load_registry(path)
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    job = job_mod.create_job(jobs, reg, "Black November", ["flyer-a5", "ig-post"], now=FIXED_NOW)
    return jobs, reg, job


def rows_for(job, statuses):
    return [dict(d, status=statuses.get(d["format_id"], "missing")) for d in job["deliverables"]]


def write(jobs, job, fid):
    d = next(d for d in job["deliverables"] if d["format_id"] == fid)
    sub = {"flyer-a5": "print", "ig-post": "social", "mall-x-door": "print"}[fid]
    p = jobs / job["id"] / "04_export" / sub / f"{d['expected_stem']}.{d['type']}"
    p.write_bytes(b"x" * 100)
    return p


def test_package_holds_only_passed_files_in_group_folders_with_notes(setup):
    jobs, _reg, job = setup
    a5 = write(jobs, job, "flyer-a5")
    write(jobs, job, "ig-post")
    rows = rows_for(job, {"flyer-a5": "ok", "ig-post": "warn"})
    rec = delivery.make_package(jobs, job["id"], rows, now=0)
    with zipfile.ZipFile(jobs / job["id"] / rec["zip"]) as z:
        names = z.namelist()
    assert names == [f"Print/{a5.name}", "README.txt"]  # the warned post waits for "send anyway"
    assert a5.read_bytes() == b"x" * 100  # copied, not moved
    assert job_mod.load_job(jobs, job["id"])["deliveries"][0]["files"] == [a5.name]


def test_send_anyway_includes_warnings_and_nothing_ready_is_a_plain_error(setup):
    jobs, _reg, job = setup
    with pytest.raises(job_mod.JobError, match="Nothing is ready"):
        delivery.make_package(jobs, job["id"], rows_for(job, {}))
    write(jobs, job, "ig-post")
    rec = delivery.make_package(jobs, job["id"], rows_for(job, {"ig-post": "warn"}),
                                include_warn=True, now=0)
    assert len(rec["files"]) == 1


def test_only_the_new_sizes_for_an_extended_campaign(setup):
    jobs, reg, job = setup
    write(jobs, job, "flyer-a5")
    job = job_mod.add_formats(jobs, job["id"], reg, ["mall-x-door"])
    door = write(jobs, job, "mall-x-door")
    rec = delivery.make_package(jobs, job["id"],
                                rows_for(job, {"flyer-a5": "ok", "mall-x-door": "ok"}),
                                batch=1, now=0)
    assert rec["files"] == [door.name] and "_add01_" in rec["zip"]
    with zipfile.ZipFile(jobs / job["id"] / rec["zip"]) as z:
        readme = z.read("README.txt").decode()
    assert "Print shop: 5 mm bleed." in readme and "Mall print/" in readme
