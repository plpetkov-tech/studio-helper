from pathlib import Path

from studio_helper.adobe import illustrator


def test_jsx_paths_resolve_to_repo_layout_and_exist():
    expected_root = Path(__file__).resolve().parents[2] / "adobe" / "illustrator"
    assert illustrator.NEW_PRINT_DOC_JSX == expected_root / "new_print_doc.jsx"
    assert illustrator.INSPECT_JSX == expected_root / "inspect.jsx"
    assert illustrator.NEW_PRINT_DOC_JSX.exists()
    assert illustrator.INSPECT_JSX.exists()


def test_create_print_doc_calls_bridge_with_expected_args(monkeypatch, tmp_path):
    calls = {}

    def fake_connect(progid):
        calls["progid"] = progid
        return "APP"

    def fake_run_jsx(app, jsx_path, args):
        calls["app"] = app
        calls["jsx_path"] = jsx_path
        calls["args"] = args
        return {"ok": True, "data": {}}

    monkeypatch.setattr(illustrator.bridge, "connect", fake_connect)
    monkeypatch.setattr(illustrator.bridge, "run_jsx", fake_run_jsx)

    job = {"id": "2026-09-25_autumn-sale"}
    result = illustrator.create_print_doc(job, tmp_path)

    assert result == {"ok": True, "data": {}}
    assert calls["progid"] == illustrator.PROGID
    assert calls["app"] == "APP"
    assert calls["jsx_path"] == illustrator.NEW_PRINT_DOC_JSX
    assert calls["args"] == {"job": job, "output_dir": str(tmp_path)}


def test_inspect_without_path_sends_empty_args(monkeypatch):
    monkeypatch.setattr(illustrator.bridge, "connect", lambda progid: "APP")
    captured = {}

    def fake_run_jsx(app, jsx_path, args):
        captured["args"] = args
        return {"ok": True, "data": {"pdf_presets": []}}

    monkeypatch.setattr(illustrator.bridge, "run_jsx", fake_run_jsx)
    illustrator.inspect()
    assert captured["args"] == {}


def test_inspect_with_path_sends_ai_path(monkeypatch, tmp_path):
    monkeypatch.setattr(illustrator.bridge, "connect", lambda progid: "APP")
    captured = {}

    def fake_run_jsx(app, jsx_path, args):
        captured["args"] = args
        return {"ok": True, "data": {}}

    monkeypatch.setattr(illustrator.bridge, "run_jsx", fake_run_jsx)
    ai_path = tmp_path / "doc.ai"
    illustrator.inspect(ai_path)
    assert captured["args"] == {"ai_path": str(ai_path)}


def test_pdf_preset_available_true(monkeypatch):
    monkeypatch.setattr(
        illustrator, "inspect", lambda ai_path=None: {"data": {"pdf_presets": ["StudioHelper_X1a"]}}
    )
    assert illustrator.pdf_preset_available("StudioHelper_X1a") is True


def test_pdf_preset_available_false(monkeypatch):
    monkeypatch.setattr(illustrator, "inspect", lambda ai_path=None: {"data": {"pdf_presets": []}})
    assert illustrator.pdf_preset_available("StudioHelper_X1a") is False


def test_is_running_delegates_to_bridge(monkeypatch):
    monkeypatch.setattr(
        illustrator.bridge, "is_running", lambda progid: progid == illustrator.PROGID
    )
    assert illustrator.is_running() is True
