import sys
import threading
import types

import pytest
from studio_helper.adobe import bridge

# Captured before any test can monkeypatch the module attribute, so
# the dedicated test below can always reach the real implementation
# regardless of the autouse fixture's patch.
_REAL_ENSURE_COM_INITIALIZED = bridge._ensure_com_initialized

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


@pytest.fixture(autouse=True)
def _no_real_com_init(monkeypatch):
    # _ensure_com_initialized does its own `import comtypes` (a
    # Windows-only, sys_platform-gated dependency -- see
    # requirements.in), so it must never run for real on the
    # ubuntu-latest CI job or on this dev machine. Tests that care
    # about its behavior replace this fixture's patch themselves.
    monkeypatch.setattr(bridge, "_ensure_com_initialized", lambda: None)


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
    assert bridge.connect("Illustrator.Application") is app


def test_connect_raises_when_launch_fails(monkeypatch):
    def raise_launch_error(progid, dynamic):
        raise RuntimeError("boom")

    fake_client = types.SimpleNamespace(
        GetActiveObject=_raise_oserror, CreateObject=raise_launch_error
    )
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    with pytest.raises(bridge.AdobeBridgeError, match="Could not start"):
        bridge.connect("Illustrator.Application")


def test_connect_calls_ensure_com_initialized_before_any_com_call(monkeypatch):
    # The bug this guards against: a background Task thread (SPEC.md
    # §6.2) calling into COM without CoInitialize, which fails with
    # "CoInitialize has not been called" (WinError -2147221008) --
    # found on a real machine, not in this test suite. connect() must
    # initialize COM on its OWN thread before touching the client.
    calls = []
    monkeypatch.setattr(bridge, "_ensure_com_initialized", lambda: calls.append("init"))

    def fake_get_active_object(progid):
        calls.append("get")
        return FakeApp()

    fake_client = types.SimpleNamespace(GetActiveObject=fake_get_active_object)
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    bridge.connect("Illustrator.Application")
    assert calls == ["init", "get"]


def test_connect_does_not_hand_a_com_object_across_threads(monkeypatch):
    # connect() must do everything -- GetActiveObject/CreateObject --
    # on the calling thread. An earlier version spawned a helper
    # thread just to enforce a timeout on CreateObject, which created
    # the COM object on that helper thread while the caller used it
    # from a different one (an apartment violation, and part of the
    # same class of bug as the missing CoInitialize).
    creating_thread_ids = []

    def fake_create(progid, dynamic):
        creating_thread_ids.append(threading.get_ident())
        return FakeApp()

    fake_client = types.SimpleNamespace(GetActiveObject=_raise_oserror, CreateObject=fake_create)
    monkeypatch.setattr(bridge, "_comtypes_client", lambda: fake_client)
    bridge.connect("Illustrator.Application")
    assert creating_thread_ids == [threading.get_ident()]


def test_ensure_com_initialized_calls_coinitialize_once_per_thread(monkeypatch):
    calls = []
    fake_comtypes = types.SimpleNamespace(CoInitialize=lambda: calls.append("CoInitialize"))
    monkeypatch.setitem(sys.modules, "comtypes", fake_comtypes)
    monkeypatch.setattr(bridge, "_ensure_com_initialized", _REAL_ENSURE_COM_INITIALIZED)
    monkeypatch.setattr(bridge._com_state, "initialized", False, raising=False)

    bridge._ensure_com_initialized()
    bridge._ensure_com_initialized()  # same thread -- must not call CoInitialize again

    assert calls == ["CoInitialize"]


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
