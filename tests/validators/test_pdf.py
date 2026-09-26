import pytest
from conftest import status_of
from studio_helper.validators import match, pdf


def test_good_pdf_all_ok(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "good_a5.pdf", print_fmt, pdf_deliverable)
    assert all(c.status == "ok" for c in checks), checks
    ids = {c.id for c in checks}
    assert ids == {
        "page-count", "trimbox", "bleedbox", "pdfx", "fonts",
        "color-space", "image-ppi", "bleed-coverage",
    }


def test_bleed_short_warns_only_left_and_bottom(fixtures_dir, print_fmt, pdf_deliverable):
    # a warning, not a fail: an edge meant to stay white paper is legitimate
    checks = pdf.validate(fixtures_dir / "bleed_short_left_bottom.pdf", print_fmt, pdf_deliverable)
    bleed_check = next(c for c in checks if c.id == "bleed-coverage")
    assert bleed_check.status == "warn"
    assert "left" in bleed_check.message
    assert "bottom" in bleed_check.message
    assert "top" not in bleed_check.message
    assert "right" not in bleed_check.message
    # everything else about this file is fine
    assert status_of(checks, "trimbox") == "ok"
    assert status_of(checks, "bleedbox") == "ok"


def test_rgb_image_fails_color_space(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "rgb_image.pdf", print_fmt, pdf_deliverable)
    assert status_of(checks, "color-space") == "fail"


def test_lowres_fails_image_ppi_only(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "lowres_150ppi.pdf", print_fmt, pdf_deliverable)
    assert status_of(checks, "image-ppi") == "fail"
    assert status_of(checks, "color-space") == "ok"
    assert status_of(checks, "bleed-coverage") == "ok"


def test_font_not_embedded_fails(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "font_not_embedded.pdf", print_fmt, pdf_deliverable)
    fonts_check = next(c for c in checks if c.id == "fonts")
    assert fonts_check.status == "fail"
    assert "Helvetica" in fonts_check.message


def test_no_bleedbox_fails_bleedbox_only(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "no_bleedbox.pdf", print_fmt, pdf_deliverable)
    assert status_of(checks, "bleedbox") == "fail"
    assert status_of(checks, "trimbox") == "ok"
    # can't check coverage without a BleedBox to render against
    assert status_of(checks, "bleed-coverage") is None


def test_no_pdfx_fails(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "no_pdfx.pdf", print_fmt, pdf_deliverable)
    assert status_of(checks, "pdfx") == "fail"


def test_multipage_fails_page_count_and_stops(fixtures_dir, print_fmt, pdf_deliverable):
    checks = pdf.validate(fixtures_dir / "two_pages.pdf", print_fmt, pdf_deliverable)
    assert len(checks) == 1
    assert checks[0].id == "page-count"
    assert checks[0].status == "fail"


def test_wrong_trimbox_size_fails(fixtures_dir, print_fmt, pdf_deliverable):
    wrong_fmt = dict(print_fmt)
    wrong_fmt["size"] = {"w": 100, "h": 100, "unit": "mm"}
    checks = pdf.validate(fixtures_dir / "good_a5.pdf", wrong_fmt, pdf_deliverable)
    assert status_of(checks, "trimbox") == "fail"


def test_panel_deliverable_uses_panel_size(fixtures_dir):
    fmt = {
        "id": "elevator-main",
        "kind": "print",
        "panels": [{"w": 148, "h": 210}, {"w": 148, "h": 210}],
        "unit": "mm",
        "bleed_mm": 3,
        "exports": ["pdf"],
        "min_image_ppi": {},
        "scale": 1,
    }
    deliverable = {"format_id": "elevator-main", "type": "pdf", "panel": 1, "expected_stem": "x"}
    checks = pdf.validate(fixtures_dir / "good_a5.pdf", fmt, deliverable)
    assert status_of(checks, "trimbox") == "ok"


def test_scaled_format_expects_scaled_trim_and_bleed(fixtures_dir, print_fmt, pdf_deliverable):
    # 1480x2100mm with 30mm bleed at 1:10 exports as an A5 PDF with 3mm bleed.
    scaled = dict(print_fmt, size={"w": 1480, "h": 2100, "unit": "mm"}, bleed_mm=30, scale=0.1)
    checks = pdf.validate(fixtures_dir / "good_a5.pdf", scaled, pdf_deliverable)
    assert status_of(checks, "trimbox") == "ok"
    assert status_of(checks, "bleedbox") == "ok"


class _Box:
    def __init__(self, w_pt, h_pt):
        self.width, self.height = w_pt, h_pt


@pytest.mark.parametrize(
    ("bleed_pt", "status"),
    [
        (8, "fail"),  # what Illustrator made of 3mm (8.5pt) before: 2.8mm, short
        (9, "ok"),  # 3mm rounded up to whole points: 3.18mm
        (3 * 72 / 25.4, "ok"),  # exactly 3mm
        (11, "fail"),  # 3.9mm: more than the round-up allows
    ],
)
def test_bleedbox_accepts_exact_or_whole_point_bleed(bleed_pt, status):
    pt = 72 / 25.4
    box = _Box(210 * pt + 2 * bleed_pt, 297 * pt + 2 * bleed_pt)
    lo, hi = match.doc_bleed_range_mm({"bleed_mm": 3, "scale": 1})
    assert pdf._check_bleedbox(box, None, 210, 297, lo, hi).status == status
