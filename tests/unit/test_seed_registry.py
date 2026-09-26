from pathlib import Path

from studio_helper import __main__ as entry
from studio_helper import paths


def _setup(tmp_path, monkeypatch):
    user = tmp_path / "user" / "registry.yaml"
    monkeypatch.setattr(paths, "user_registry_path", lambda: user)
    monkeypatch.setattr(
        paths, "ensure_app_data_dirs", lambda: user.parent.mkdir(parents=True, exist_ok=True)
    )
    return user, paths.bundled_registry_path().read_bytes()


def test_fresh_install_gets_bundled_default(tmp_path, monkeypatch):
    user, bundled = _setup(tmp_path, monkeypatch)
    entry.seed_user_registry()
    assert user.read_bytes() == bundled


def test_untouched_old_default_is_upgraded_with_backup(tmp_path, monkeypatch):
    user, bundled = _setup(tmp_path, monkeypatch)
    fixture = Path(__file__).parents[1] / "fixtures" / "registry_v0_placeholder.yaml"
    old = fixture.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")  # Windows copy
    user.parent.mkdir(parents=True)
    user.write_bytes(old)
    entry.seed_user_registry()
    assert user.read_bytes() == bundled
    assert user.with_suffix(".yaml.bak").read_bytes() == old


def test_user_edited_registry_is_left_alone(tmp_path, monkeypatch):
    user, _ = _setup(tmp_path, monkeypatch)
    user.parent.mkdir(parents=True)
    user.write_text("version: 1\nformats: []\n# mine\n")
    entry.seed_user_registry()
    assert user.read_text().endswith("# mine\n")
    assert not user.with_suffix(".yaml.bak").exists()
