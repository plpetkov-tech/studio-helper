import pytest
from studio_helper.core.scaffold import create_job_folder


def test_creates_expected_tree(tmp_path):
    job_root = tmp_path / "2026-09-25_autumn-sale"
    create_job_folder(job_root)

    expected = [
        "01_brief",
        "02_assets",
        "03_working",
        "04_export/print",
        "04_export/led",
        "04_export/web",
        "04_export/social",
    ]
    for rel in expected:
        assert (job_root / rel).is_dir()


def test_refuses_to_recreate_existing_job(tmp_path):
    job_root = tmp_path / "2026-09-25_autumn-sale"
    create_job_folder(job_root)
    with pytest.raises(FileExistsError):
        create_job_folder(job_root)
