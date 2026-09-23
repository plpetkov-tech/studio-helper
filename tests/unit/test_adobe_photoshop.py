from pathlib import Path

from studio_helper.adobe import photoshop


def test_jsx_paths_resolve_to_repo_layout_and_exist():
    expected_root = Path(__file__).resolve().parents[2] / "adobe" / "photoshop"
    assert photoshop.NEW_DIGITAL_DOC_JSX == expected_root / "new_digital_doc.jsx"
    assert photoshop.EXPORT_DIGITAL_JSX == expected_root / "export_digital.jsx"
    assert photoshop.NEW_DIGITAL_DOC_JSX.exists()
    assert photoshop.EXPORT_DIGITAL_JSX.exists()


def test_create_digital_doc_calls_bridge_with_expected_args(monkeypatch, tmp_path):
    calls = {}

    def fake_connect(progid):
        calls["progid"] = progid
        return "APP"

    def fake_run_jsx(app, jsx_path, args):
        calls["app"] = app
        calls["jsx_path"] = jsx_path
        calls["args"] = args
        return {"ok": True, "data": {}}

    monkeypatch.setattr(photoshop.bridge, "connect", fake_connect)
    monkeypatch.setattr(photoshop.bridge, "run_jsx", fake_run_jsx)

    job = {"id": "2026-09-25_autumn-sale"}
    result = photoshop.create_digital_doc(job, tmp_path)

    assert result == {"ok": True, "data": {}}
    assert calls["progid"] == photoshop.PROGID
    assert calls["jsx_path"] == photoshop.NEW_DIGITAL_DOC_JSX
    assert calls["args"] == {"job": job, "output_dir": str(tmp_path)}


def test_export_digital_converts_export_dirs_to_strings(monkeypatch, tmp_path):
    monkeypatch.setattr(photoshop.bridge, "connect", lambda progid: "APP")
    captured = {}

    def fake_run_jsx(app, jsx_path, args):
        captured["jsx_path"] = jsx_path
        captured["args"] = args
        return {"ok": True, "data": {"exported": []}}

    monkeypatch.setattr(photoshop.bridge, "run_jsx", fake_run_jsx)

    psd_path = tmp_path / "job_digital_v01.psd"
    export_dirs = {
        "social": tmp_path / "04_export" / "social",
        "screen": tmp_path / "04_export" / "led",
    }
    photoshop.export_digital({"id": "x"}, psd_path, export_dirs)

    assert captured["jsx_path"] == photoshop.EXPORT_DIGITAL_JSX
    assert captured["args"] == {
        "job": {"id": "x"},
        "psd_path": str(psd_path),
        "export_dirs": {
            "social": str(tmp_path / "04_export" / "social"),
            "screen": str(tmp_path / "04_export" / "led"),
        },
    }


def test_is_running_delegates_to_bridge(monkeypatch):
    monkeypatch.setattr(
        photoshop.bridge, "is_running", lambda progid: progid == photoshop.PROGID
    )
    assert photoshop.is_running() is True
