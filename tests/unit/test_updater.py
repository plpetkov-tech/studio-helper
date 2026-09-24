"""updater.py (SPEC.md §15, 2026-09-24): the one place in the app
allowed to touch the network, and only when the user clicks a button.
Every test here mocks urllib -- no real network calls in the suite."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile

import pytest
from studio_helper import updater


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen_returning(mapping):
    """mapping: {url: bytes}. Raises AssertionError for unexpected URLs."""

    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if url not in mapping:
            raise AssertionError(f"unexpected URL requested: {url}")
        return _FakeResponse(mapping[url])

    return _urlopen


# -- version comparison -------------------------------------------------


@pytest.mark.parametrize(
    "current,latest,expected",
    [
        ("0.3.0", "v0.3.1", True),
        ("0.3.0", "0.3.0", False),
        ("0.3.1", "v0.3.0", False),
        ("0.9.0", "v0.10.0", True),
        ("1.0.0", "2.0.0", True),
        ("0.3.0", "not-a-real-tag", False),
    ],
)
def test_is_newer(current, latest, expected):
    assert updater.is_newer(current, latest) is expected


# -- check_for_update ----------------------------------------------------


def test_check_for_update_parses_release(monkeypatch):
    release = {
        "tag_name": "v99.0.0",
        "body": "Adds an auto-updater.",
        "html_url": "https://github.com/plpetkov-tech/studio-helper/releases/tag/v99.0.0",
        "assets": [
            {"name": "StudioHelper-v99.0.0.zip", "browser_download_url": "https://x/zip"},
            {"name": "SHA256SUMS", "browser_download_url": "https://x/sums"},
            {"name": "SBOM.cdx.json", "browser_download_url": "https://x/sbom"},
        ],
    }
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        _fake_urlopen_returning({updater.API_URL: json.dumps(release).encode()}),
    )

    info = updater.check_for_update()
    assert info.latest_version == "99.0.0"
    assert info.available is True
    assert info.zip_url == "https://x/zip"
    assert info.zip_name == "StudioHelper-v99.0.0.zip"
    assert info.sha256sums_url == "https://x/sums"
    assert info.notes == "Adds an auto-updater."


def test_check_for_update_not_available_when_current(monkeypatch):
    release = {"tag_name": f"v{updater.__version__}", "assets": []}
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        _fake_urlopen_returning({updater.API_URL: json.dumps(release).encode()}),
    )
    info = updater.check_for_update()
    assert info.available is False


def test_check_for_update_network_failure_raises_update_error(monkeypatch):
    def _boom(req, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr(updater.urllib.request, "urlopen", _boom)
    with pytest.raises(updater.UpdateError, match="Could not reach GitHub"):
        updater.check_for_update()


# -- download_and_stage: checksum verification ---------------------------


def _make_zip_bytes(top_dir_name: str, files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, content in files.items():
            zf.writestr(f"{top_dir_name}/{rel}", content)
    return buf.getvalue()


def _info(tmp_zip_bytes, zip_name="StudioHelper-v9.9.9.zip", latest="9.9.9"):
    sha = hashlib.sha256(tmp_zip_bytes).hexdigest()
    sums_text = f"{sha}  {zip_name}\n"
    return (
        updater.UpdateInfo(
            current_version="0.1.0",
            latest_version=latest,
            available=True,
            notes="",
            html_url="https://x",
            zip_url="https://x/zip",
            zip_name=zip_name,
            sha256sums_url="https://x/sums",
        ),
        sums_text.encode(),
    )


def test_download_and_stage_rejects_checksum_mismatch(monkeypatch, tmp_path):
    zip_bytes = _make_zip_bytes("StudioHelper-v9.9.9", {"app/x.txt": "hi"})
    info, _real_sums = _info(zip_bytes)
    wrong_sums = b"0" * 64 + b"  StudioHelper-v9.9.9.zip\n"

    monkeypatch.setattr(updater.paths, "bundled_root", lambda: tmp_path / "StudioHelper-v0.1.0")
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        _fake_urlopen_returning({"https://x/zip": zip_bytes, "https://x/sums": wrong_sums}),
    )

    with pytest.raises(updater.UpdateError, match="checksum doesn't match"):
        updater.download_and_stage(info)


def test_download_and_stage_extracts_to_sibling_dir(monkeypatch, tmp_path):
    install_root = tmp_path
    current = install_root / "StudioHelper-v0.1.0"
    current.mkdir()

    zip_bytes = _make_zip_bytes(
        "StudioHelper-v9.9.9",
        {"app/x.txt": "hi", "Start Studio Helper.bat": "@echo off"},
    )
    info, sums_bytes = _info(zip_bytes)

    monkeypatch.setattr(updater.paths, "bundled_root", lambda: current)
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        _fake_urlopen_returning({"https://x/zip": zip_bytes, "https://x/sums": sums_bytes}),
    )

    result = updater.download_and_stage(info)

    assert result == install_root / "StudioHelper-v9.9.9"
    assert (result / "app" / "x.txt").read_text() == "hi"
    # nothing left behind
    assert list(install_root.glob(".studiohelper-update-staging-*")) == []
    # the currently-running install was never touched
    assert current.exists()


def test_download_and_stage_rejects_zip_slip(monkeypatch, tmp_path):
    install_root = tmp_path
    current = install_root / "StudioHelper-v0.1.0"
    current.mkdir()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")
    zip_bytes = buf.getvalue()
    info, sums_bytes = _info(zip_bytes)

    monkeypatch.setattr(updater.paths, "bundled_root", lambda: current)
    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        _fake_urlopen_returning({"https://x/zip": zip_bytes, "https://x/sums": sums_bytes}),
    )

    with pytest.raises(updater.UpdateError, match="unsafe path"):
        updater.download_and_stage(info)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_download_and_stage_missing_assets_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.paths, "bundled_root", lambda: tmp_path)
    info = updater.UpdateInfo(
        current_version="0.1.0",
        latest_version="9.9.9",
        available=True,
        notes="",
        html_url="https://x",
        zip_url=None,
        zip_name=None,
        sha256sums_url=None,
    )
    with pytest.raises(updater.UpdateError, match="missing its zip"):
        updater.download_and_stage(info)


# -- schedule_relaunch ----------------------------------------------------


def test_schedule_relaunch_refuses_on_non_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(updater.UpdateError, match="only supported on Windows"):
        updater.schedule_relaunch(tmp_path)


def test_schedule_relaunch_launches_detached_powershell(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(updater.paths, "bundled_root", lambda: tmp_path / "StudioHelper-v0.1.0")
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))

    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)

    updater.schedule_relaunch(tmp_path / "StudioHelper-v9.9.9")

    args = captured["args"]
    assert args[0] == "powershell"
    assert "-ExecutionPolicy" in args
    assert "Bypass" in args
    assert str(tmp_path / "StudioHelper-v9.9.9") in args
    assert captured["kwargs"]["close_fds"] is True


def test_relaunch_script_renames_old_install_instead_of_deleting_it():
    """A release that fails to start must still leave a working copy
    behind (SPEC.md §15, 2026-09-24) -- the old install is renamed to
    "<OldDir>.previous", never deleted outright. Only a *stale*
    ".previous" from the update before last is removed."""
    script = updater._RELAUNCH_PS1

    assert "Rename-Item" in script
    assert '$previousDir = "$OldDir.previous"' in script
    # The only Remove-Item targeting a whole folder tree must be scoped
    # to $previousDir (the stale backup), never bare $OldDir.
    for line in script.splitlines():
        if "Remove-Item" in line and "-Recurse" in line:
            assert "$previousDir" in line
            assert "$OldDir" not in line
