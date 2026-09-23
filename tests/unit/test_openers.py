import subprocess
import sys

from studio_helper.api import openers


def test_open_path_swallows_timeout(monkeypatch, tmp_path):
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="xdg-open", timeout=5)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", raise_timeout)
    openers.open_path(tmp_path, reveal=True)  # must not raise


def test_open_path_swallows_oserror(monkeypatch, tmp_path):
    def raise_oserror(*args, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", raise_oserror)
    openers.open_path(tmp_path, reveal=True)  # must not raise


def test_open_path_passes_timeout_to_subprocess(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, check, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", fake_run)
    openers.open_path(tmp_path, reveal=True)
    assert captured["timeout"] == openers.OPEN_TIMEOUT_SECONDS
    assert captured["cmd"][0] == "explorer.exe"
