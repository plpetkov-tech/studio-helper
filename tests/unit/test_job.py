from datetime import UTC, datetime

import pytest
from studio_helper.core import job as job_mod
from studio_helper.core.registry import load_registry

REGISTRY_YAML = """\
version: 3
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
  - id: elevator-main
    name: Elevator doors
    kind: print
    panels:
      - {w: 900, h: 2100}
      - {w: 900, h: 2100}
    panel_gap_mm: 20
    unit: mm
    exports: [pdf]
job_types:
  full-campaign: [flyer-a5, ig-post]
"""

FIXED_NOW = datetime(2026, 9, 25, 15, 2, 11, tzinfo=UTC)


@pytest.fixture()
def registry(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY_YAML, encoding="utf-8")
    return load_registry(path)


@pytest.fixture()
def jobs_root(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    return root


def test_create_job_basic_shape(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)

    assert job["id"] == "2026-09-25_autumn-sale"
    assert job["slug"] == "autumn-sale"
    assert job["schema_version"] == 1
    assert job["registry_version"] == 3
    assert job["version"] == 1
    assert job["files"] == {"print": [], "psd": None}
    assert len(job["formats"]) == 1
    assert job["formats"][0]["bleed_mm"] == 3  # inherited from print_defaults


def test_create_job_writes_job_json(jobs_root, registry):
    job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    job_file = jobs_root / "2026-09-25_autumn-sale" / "job.json"
    assert job_file.exists()


def test_create_job_scaffolds_folders(jobs_root, registry):
    job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    root = jobs_root / "2026-09-25_autumn-sale"
    assert (root / "04_export" / "print").is_dir()
    assert (root / "03_working").is_dir()


def test_create_job_cyrillic_name_transliterated(jobs_root, registry):
    job = job_mod.create_job(
        jobs_root, registry, "Есенна разпродажба", ["flyer-a5"], now=FIXED_NOW
    )
    assert job["slug"] == "esenna-razprodazhba"
    assert job["id"] == "2026-09-25_esenna-razprodazhba"


def test_create_job_deliverables_for_simple_format(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    assert job["deliverables"] == [
        {
            "format_id": "flyer-a5",
            "type": "pdf",
            "panel": None,
            "expected_stem": "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01",
        }
    ]


def test_create_job_deliverables_for_panels(jobs_root, registry):
    job = job_mod.create_job(
        jobs_root, registry, "Autumn Sale", ["elevator-main"], now=FIXED_NOW
    )
    stems = [d["expected_stem"] for d in job["deliverables"]]
    assert stems == [
        "2026-09-25_autumn-sale_elevator-main_900x2100mm_p1_v01",
        "2026-09-25_autumn-sale_elevator-main_900x2100mm_p2_v01",
    ]
    assert [d["panel"] for d in job["deliverables"]] == [1, 2]


def test_create_job_multiple_formats(jobs_root, registry):
    job = job_mod.create_job(
        jobs_root, registry, "Autumn Sale", ["flyer-a5", "ig-post"], now=FIXED_NOW
    )
    format_ids = {d["format_id"] for d in job["deliverables"]}
    assert format_ids == {"flyer-a5", "ig-post"}


def test_create_job_empty_name_rejected(jobs_root, registry):
    with pytest.raises(job_mod.JobError):
        job_mod.create_job(jobs_root, registry, "   ", ["flyer-a5"], now=FIXED_NOW)


def test_create_job_no_formats_rejected(jobs_root, registry):
    with pytest.raises(job_mod.JobError):
        job_mod.create_job(jobs_root, registry, "Autumn Sale", [], now=FIXED_NOW)


def test_create_job_unknown_format_rejected(jobs_root, registry):
    with pytest.raises(job_mod.JobError, match="Unknown format"):
        job_mod.create_job(jobs_root, registry, "Autumn Sale", ["nope"], now=FIXED_NOW)


def test_create_job_name_collision_gets_suffix(jobs_root, registry):
    job1 = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    job2 = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    assert job1["id"] != job2["id"]
    assert job2["id"] == "2026-09-25_autumn-sale-2"
    assert job2["slug"] == "autumn-sale-2"
    # deliverable names must reflect the deduped slug too, or the two jobs'
    # exports would collide on disk
    assert "autumn-sale-2" in job2["deliverables"][0]["expected_stem"]


def test_load_job_roundtrip(jobs_root, registry):
    created = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    loaded = job_mod.load_job(jobs_root, created["id"])
    assert loaded == created


def test_load_job_missing_raises(jobs_root):
    with pytest.raises(job_mod.JobError):
        job_mod.load_job(jobs_root, "does-not-exist")


def test_job_path_rejects_traversal(jobs_root):
    with pytest.raises(job_mod.JobError):
        job_mod.job_path(jobs_root, "../../etc")


def test_list_jobs_returns_newest_first(jobs_root, registry):
    job_mod.create_job(jobs_root, registry, "A", ["flyer-a5"], now=FIXED_NOW)
    job_mod.create_job(
        jobs_root, registry, "B", ["flyer-a5"],
        now=FIXED_NOW.replace(day=26),
    )
    jobs = job_mod.list_jobs(jobs_root)
    assert jobs[0]["id"].startswith("2026-09-26")


def test_list_jobs_empty_when_no_root(tmp_path):
    assert job_mod.list_jobs(tmp_path / "nonexistent") == []


def test_bump_version_increments(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    bumped = job_mod.bump_version(jobs_root, job["id"])
    assert bumped["version"] == 2
    assert bumped["deliverables"][0]["expected_stem"].endswith("_v02")


def test_bump_version_persists(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    job_mod.bump_version(jobs_root, job["id"])
    reloaded = job_mod.load_job(jobs_root, job["id"])
    assert reloaded["version"] == 2


def test_bump_version_keeps_job_id_stable(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    bumped = job_mod.bump_version(jobs_root, job["id"])
    assert bumped["id"] == job["id"]


def test_record_digital_file_stores_relative_path(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    root = jobs_root / job["id"]
    psd_path = root / "03_working" / f"{job['id']}_digital_v01.psd"
    updated = job_mod.record_digital_file(jobs_root, job["id"], str(psd_path))
    assert updated["files"]["psd"] == f"03_working/{job['id']}_digital_v01.psd"


def test_record_digital_file_persists(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    root = jobs_root / job["id"]
    psd_path = root / "03_working" / f"{job['id']}_digital_v01.psd"
    job_mod.record_digital_file(jobs_root, job["id"], str(psd_path))
    reloaded = job_mod.load_job(jobs_root, job["id"])
    assert reloaded["files"]["psd"] == f"03_working/{job['id']}_digital_v01.psd"


def test_record_digital_file_overwrites_previous_value(jobs_root, registry):
    job = job_mod.create_job(jobs_root, registry, "Autumn Sale", ["flyer-a5"], now=FIXED_NOW)
    root = jobs_root / job["id"]
    job_mod.record_digital_file(jobs_root, job["id"], str(root / "a.psd"))
    updated = job_mod.record_digital_file(jobs_root, job["id"], str(root / "b.psd"))
    assert updated["files"]["psd"] == "b.psd"
