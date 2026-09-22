from pathlib import Path

from studio_helper import paths


def test_app_data_dir_ends_with_app_name():
    assert paths.app_data_dir().name == "StudioHelper"


def test_default_jobs_root_under_documents():
    assert paths.default_jobs_root().name == "Studio Jobs"


def test_is_inside_accepts_nested_path(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    nested = root / "2026-09-25_autumn-sale" / "job.json"
    nested.parent.mkdir(parents=True)
    nested.touch()
    assert paths.is_inside(nested, root)


def test_is_inside_rejects_escape(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.touch()
    assert not paths.is_inside(outside, root)


def test_is_inside_rejects_dotdot_traversal(tmp_path):
    root = tmp_path / "jobs"
    root.mkdir()
    escape = root / ".." / "secret.txt"
    assert not paths.is_inside(escape, root)


def test_bundled_registry_path_matches_repo_layout():
    # app/studio_helper/paths.py -> parents[2] must be the repo root
    # that also contains defaults/registry.yaml (SPEC.md §5.1).
    expected = Path(__file__).resolve().parents[2] / "defaults" / "registry.yaml"
    assert paths.bundled_registry_path() == expected
