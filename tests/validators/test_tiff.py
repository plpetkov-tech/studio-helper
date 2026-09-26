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


def test_scaled_format_expects_scaled_document_pixels(fixtures_dir, print_fmt, tiff_deliverable):
    # A 1480x2100mm format with 30mm bleed drawn at 1:10 is a 148x210mm
    # artboard with 3mm bleed, exported at tiff_ppi / scale = 15 / 0.1 =
    # 150ppi -- exactly what good_a5.tiff is.
    scaled = dict(
        print_fmt, size={"w": 1480, "h": 2100, "unit": "mm"}, bleed_mm=30, scale=0.1, tiff_ppi=15
    )
    checks = tiff.validate(fixtures_dir / "good_a5.tiff", scaled, tiff_deliverable)
    assert status_of(checks, "dimensions") == "ok"
