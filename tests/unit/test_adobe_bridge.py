import sys
import threading
import types

import pytest
from studio_helper.adobe import bridge

DEFAULT_OK_RESULT = '{"ok": true, "data": {}, "errors": [], "warnings": []}'


class FakeApp:
    def __init__(self, dojavascript_return=DEFAULT_OK_RESULT):
        self.calls = []
        self._return = dojavascript_return

    def DoJavaScript(self, code):
        self.calls.append(code)
        return self._return


def _raise_oserror(_progid):
    raise OSError("not running")


def test_is_running_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert bridge.is_running("Illustrator.Application") is False


def test_is_running_true_when_active_object_found(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    fake_client = types.SimpleNamespace(GetActiveObject=lambda progid: FakeApp())
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    assert bridge.is_running("Illustrator.Application") is True


def test_is_running_false_when_not_running(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    fake_client = types.SimpleNamespace(GetActiveObject=_raise_oserror)
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    assert bridge.is_running("Illustrator.Application") is False


def test_connect_returns_active_object_if_running(monkeypatch):
    app = FakeApp()
    fake_client = types.SimpleNamespace(GetActiveObject=lambda progid: app)
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    assert bridge.connect("Illustrator.Application") is app


def test_connect_launches_when_not_running(monkeypatch):
    app = FakeApp()
    fake_client = types.SimpleNamespace(
        GetActiveObject=_raise_oserror,
        CreateObject=lambda progid, dynamic: app,
    )
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    assert bridge.connect("Illustrator.Application", timeout=5) is app


def test_connect_raises_when_launch_fails(monkeypatch):
    def raise_launch_error(progid, dynamic):
        raise RuntimeError("boom")

    fake_client = types.SimpleNamespace(
        GetActiveObject=_raise_oserror, CreateObject=raise_launch_error
    )
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    with pytest.raises(bridge.AdobeBridgeError, match="Could not start"):
        bridge.connect("Illustrator.Application", timeout=5)


def test_connect_raises_on_timeout(monkeypatch):
    def slow_create(progid, dynamic):
        threading.Event().wait(5)
        return FakeApp()

    fake_client = types.SimpleNamespace(GetActiveObject=_raise_oserror, CreateObject=slow_create)
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    with pytest.raises(bridge.AdobeBridgeError, match="did not start"):
        bridge.connect("Illustrator.Application", timeout=0.2)


def test_run_jsx_sends_args_and_evalfile_call(tmp_path):
    app = FakeApp()
    result = bridge.run_jsx(app, tmp_path / "script.jsx", {"job": {"id": "x"}})
    assert result == {"ok": True, "data": {}, "errors": [], "warnings": []}
    assert len(app.calls) == 1
    assert "SH_ARGS" in app.calls[0]
    assert "$.evalFile(" in app.calls[0]


def test_run_jsx_uses_forward_slashes_for_windows_paths():
    app = FakeApp()
    bridge.run_jsx(app, "C:\\Program Files\\StudioHelper\\adobe\\illustrator\\script.jsx", {})
    eval_file_arg = app.calls[0].split("$.evalFile(", 1)[1]
    assert "\\" not in eval_file_arg


def test_run_jsx_never_string_concatenates_args(tmp_path):
    # A value with a quote must come out safely escaped by json.dumps,
    # not hand-concatenated into the code string (SPEC.md §8).
    app = FakeApp()
    bridge.run_jsx(app, tmp_path / "x.jsx", {"name": 'a"; nasty(); "'})
    assert '\\"' in app.calls[0]


def test_run_jsx_raises_on_dojavascript_exception(tmp_path):
    class FailingApp:
        def DoJavaScript(self, code):
            raise RuntimeError("COM error")

    with pytest.raises(bridge.AdobeBridgeError, match="reported an error"):
        bridge.run_jsx(FailingApp(), tmp_path / "x.jsx", {})


def test_run_jsx_raises_on_invalid_json_result(tmp_path):
    app = FakeApp(dojavascript_return="not json")
    with pytest.raises(bridge.AdobeBridgeError, match="unexpected result"):
        bridge.run_jsx(app, tmp_path / "x.jsx", {})


def test_run_jsx_raises_on_none_result(tmp_path):
    app = FakeApp(dojavascript_return=None)
    with pytest.raises(bridge.AdobeBridgeError, match="unexpected result"):
        bridge.run_jsx(app, tmp_path / "x.jsx", {})
