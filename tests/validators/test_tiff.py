from conftest import status_of
from studio_helper.validators import tiff


def test_good_tiff_all_ok(fixtures_dir, print_fmt, tiff_deliverable):
    checks = tiff.validate(fixtures_dir / "good_a5.tiff", print_fmt, tiff_deliverable)
    assert all(c.status == "ok" for c in checks), checks
    ids = {c.id for c in checks}
    assert ids == {"color-mode", "dimensions", "dpi-tag"}


def test_wrong_mode_fails(fixtures_dir, print_fmt, tiff_deliverable):
    checks = tiff.validate(fixtures_dir / "wrong_mode.tiff", print_fmt, tiff_deliverable)
    assert status_of(checks, "color-mode") == "fail"
    assert status_of(checks, "dimensions") == "ok"


def test_wrong_dimensions_fail(fixtures_dir, print_fmt, tiff_deliverable):
    wrong_fmt = dict(print_fmt)
    wrong_fmt["tiff_ppi"] = 300  # good_a5.tiff was rendered at 150ppi
    checks = tiff.validate(fixtures_dir / "good_a5.tiff", wrong_fmt, tiff_deliverable)
    assert status_of(checks, "dimensions") == "fail"
