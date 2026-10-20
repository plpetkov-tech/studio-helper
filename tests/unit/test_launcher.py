from pathlib import Path

import pytest
from studio_helper import launcher


class FakeIO:
    def __init__(self, desktop: Path):
        self._desktop = desktop
        self.targets: dict[Path, str] = {}
        self.writes = 0

    def desktop(self):
        return self._desktop

    def read_target(self, lnk):
        return self.targets.get(lnk)

    def write(self, lnk, target, args, workdir, icon):
        lnk.write_bytes(b"lnk")
        self.targets[lnk] = str(target)
        self.writes += 1


class Cfg:
    desktop_shortcut_created = False
    saved = 0

    def save(self):
        self.saved += 1


@pytest.fixture()
def install(tmp_path):
    root = tmp_path / "StudioHelper-v1.0.0"
    (root / "runtime").mkdir(parents=True)
    (root / "runtime" / "pythonw.exe").write_bytes(b"")
    return root


@pytest.fixture()
def desktop(tmp_path):
    d = tmp_path / "Desktop"
    d.mkdir()
    return d


def test_launcher_files_point_at_this_install(tmp_path, monkeypatch, install):
    monkeypatch.setattr(launcher.paths, "app_data_dir", lambda: tmp_path / "data")
    assert set(launcher.write_launchers(install)) == {
        launcher.START_CMD, launcher.MCP_CMD, "studio-helper-SKILL.md"}
    start = (tmp_path / "data" / "launcher" / launcher.START_CMD).read_text()
    assert "pythonw.exe" in start and str(install) in start
    mcp = (tmp_path / "data" / "launcher" / launcher.MCP_CMD).read_text()
    assert "python.exe" in mcp and "--mcp" in mcp and "pythonw" not in mcp
    assert launcher.write_launchers(install) == []  # unchanged: nothing rewritten


def test_created_once_then_follows_updates(tmp_path, install, desktop):
    io, cfg = FakeIO(desktop), Cfg()
    assert launcher.ensure_desktop_shortcut(install, cfg, io) == "created"
    assert cfg.desktop_shortcut_created and cfg.saved == 1
    assert launcher.ensure_desktop_shortcut(install, cfg, io) == "unchanged"

    newer = tmp_path / "StudioHelper-v1.0.1"
    (newer / "runtime").mkdir(parents=True)
    (newer / "runtime" / "pythonw.exe").write_bytes(b"")
    assert launcher.ensure_desktop_shortcut(newer, cfg, io) == "updated"
    assert io.targets[desktop / launcher.SHORTCUT_NAME].startswith(str(newer))


def test_deleted_shortcut_is_not_recreated(install, desktop):
    io, cfg = FakeIO(desktop), Cfg()
    launcher.ensure_desktop_shortcut(install, cfg, io)
    (desktop / launcher.SHORTCUT_NAME).unlink()
    assert launcher.ensure_desktop_shortcut(install, cfg, io) == "deleted-by-user"
    assert not (desktop / launcher.SHORTCUT_NAME).exists()


def test_her_own_shortcut_with_the_same_name_is_left_alone(install, desktop):
    io, cfg = FakeIO(desktop), Cfg()
    lnk = desktop / launcher.SHORTCUT_NAME
    lnk.write_bytes(b"hers")
    io.targets[lnk] = r"C:\Tools\something-else.exe"
    assert launcher.ensure_desktop_shortcut(install, cfg, io) == "foreign"
    assert lnk.read_bytes() == b"hers" and io.writes == 0
    assert launcher.remove_desktop_shortcut(io) is False and lnk.exists()


def test_dev_checkout_without_runtime_is_skipped(tmp_path, desktop):
    assert launcher.ensure_desktop_shortcut(tmp_path, Cfg(), FakeIO(desktop)) == "skipped"


@pytest.mark.parametrize("target,ours", [
    (r"C:\Users\m\StudioHelper-v0.5.2\runtime\pythonw.exe", True),
    (r"D:\Apps\StudioHelper-v1.0.0\runtime\PYTHONW.EXE", True),
    (r"C:\Python312\pythonw.exe", False),
    (None, False),
])
def test_is_ours(target, ours):
    assert launcher.is_ours(target) is ours
