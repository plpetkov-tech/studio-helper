import sys

from studio_helper.adobe.bridge import AdobeBridgeError
from studio_helper.api import setup_check
from studio_helper.api.context import AppContext
from studio_helper.config import Config

REGISTRY_YAML = """\
version: 1
formats:
  - id: flyer-a5
    name: A5 flyer
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]
"""


def _ctx(tmp_path, jobs_root=None):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(REGISTRY_YAML, encoding="utf-8")
    jr = jobs_root or (tmp_path / "jobs")
    return AppContext(Config(jobs_root=str(jr), registry_path=str(registry_path)))


def test_check_registry_ok(tmp_path):
    ctx = _ctx(tmp_path)
    result = setup_check._check_registry(ctx)
    assert result["ok"] is True


def test_check_registry_fails_on_invalid_yaml(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.registry_path.write_text("version: 1\nformats: not-a-list\n", encoding="utf-8")
    result = setup_check._check_registry(ctx)
    assert result["ok"] is False
    assert result["hint"]


def test_check_jobs_folder_ok(tmp_path):
    ctx = _ctx(tmp_path)
    result = setup_check._check_jobs_folder(ctx)
    assert result["ok"] is True


def test_check_jobs_folder_fails_when_path_blocked(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    ctx = _ctx(tmp_path, jobs_root=blocker / "jobs")
    result = setup_check._check_jobs_folder(ctx)
    assert result["ok"] is False


def _presets(monkeypatch, names):
    monkeypatch.setattr(
        setup_check.illustrator, "inspect", lambda ai_path=None: {"data": {"pdf_presets": names}}
    )


def test_check_illustrator_and_preset_when_unreachable(monkeypatch, tmp_path):
    def fake_inspect(ai_path=None):
        raise AdobeBridgeError("Illustrator automation is only available on Windows.")

    monkeypatch.setattr(setup_check.illustrator, "inspect", fake_inspect)
    illustrator_check, preset_check = setup_check._check_illustrator_and_preset(_ctx(tmp_path))
    assert illustrator_check["ok"] is False
    assert preset_check["ok"] is False


def test_preset_defaults_to_builtin_pdfx_when_registry_names_none(monkeypatch, tmp_path):
    _presets(monkeypatch, ["[High Quality Print]", "[PDF/X-1a:2001]"])
    illustrator_check, preset_check = setup_check._check_illustrator_and_preset(_ctx(tmp_path))
    assert illustrator_check["ok"] is True
    assert preset_check["ok"] is True
    assert "[PDF/X-1a:2001]" in preset_check["message"]


def test_named_preset_missing_explains_the_fallback(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    ctx.registry_path.write_text(
        REGISTRY_YAML.replace(
            "formats:", "print_defaults:\n  pdf_preset: StudioHelper_X1a\nformats:"
        ),
        encoding="utf-8",
    )
    _presets(monkeypatch, ["[PDF/X-1a:2001]"])
    _ill, preset_check = setup_check._check_illustrator_and_preset(ctx)
    assert preset_check["ok"] is False
    assert "use '[PDF/X-1a:2001]' instead" in preset_check["message"]
    assert "SPEC.md" not in preset_check["hint"]


def test_named_preset_found(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    ctx.registry_path.write_text(
        REGISTRY_YAML.replace("formats:", "print_defaults:\n  pdf_preset: Print Shop X\nformats:"),
        encoding="utf-8",
    )
    _presets(monkeypatch, ["Print Shop X"])
    assert setup_check._check_illustrator_and_preset(ctx)[1]["ok"] is True


def test_mark_of_the_web_not_applicable_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    result = setup_check._check_mark_of_the_web()
    assert result["ok"] is True
    assert "Not applicable" in result["message"]


def test_mark_of_the_web_ok_in_dev_checkout(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(setup_check.paths, "bundled_root", lambda: tmp_path)
    result = setup_check._check_mark_of_the_web()
    assert result["ok"] is True
    assert "dev checkout" in result["message"]


def test_mark_of_the_web_fails_when_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(setup_check.paths, "bundled_root", lambda: tmp_path)
    bat = tmp_path / "Start Studio Helper.bat"
    bat.write_text("@echo off", encoding="utf-8")
    # Not a real NTFS ADS (this runs on any filesystem) -- the check
    # itself is just a path-string existence check, so this exercises
    # the same code path a real Zone.Identifier stream would.
    (tmp_path / "Start Studio Helper.bat:Zone.Identifier").write_text("", encoding="utf-8")

    result = setup_check._check_mark_of_the_web()
    assert result["ok"] is False
    assert "Unblock" in result["hint"]


def test_mark_of_the_web_ok_when_not_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(setup_check.paths, "bundled_root", lambda: tmp_path)
    (tmp_path / "Start Studio Helper.bat").write_text("@echo off", encoding="utf-8")

    result = setup_check._check_mark_of_the_web()
    assert result["ok"] is True


def test_run_all_checks_returns_five_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")  # skip the mark-of-the-web filesystem specifics
    monkeypatch.setattr(
        setup_check.illustrator, "inspect", lambda ai_path=None: {"data": {"pdf_presets": []}}
    )
    ctx = _ctx(tmp_path)
    result = setup_check.run_all_checks(ctx)
    ids = {c["id"] for c in result["checks"]}
    assert ids == {"registry", "jobs_folder", "illustrator", "pdf_preset", "mark_of_the_web"}
