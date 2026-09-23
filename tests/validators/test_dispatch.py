"""End-to-end: validate_file() routes a real file to the right
validator by matching it against a job's deliverables (SPEC.md §6.7)."""

import shutil

from studio_helper.validators import validate_file


def _job(fmt: dict, deliverable: dict) -> dict:
    return {"formats": [fmt], "deliverables": [deliverable]}


def test_validate_file_routes_pdf(fixtures_dir, print_fmt, pdf_deliverable, tmp_path):
    named = tmp_path / (pdf_deliverable["expected_stem"] + ".pdf")
    shutil.copyfile(fixtures_dir / "good_a5.pdf", named)

    result = validate_file(named, _job(print_fmt, pdf_deliverable))
    assert result.status == "ok"
    assert result.format_id == "flyer-a5"
    assert result.deliverable == pdf_deliverable


def test_validate_file_unmatched_filename_is_warn(tmp_path, print_fmt, pdf_deliverable):
    stray = tmp_path / "not_a_deliverable.pdf"
    stray.write_bytes(b"%PDF-1.4 fake")

    result = validate_file(stray, _job(print_fmt, pdf_deliverable))
    assert result.status == "warn"
    assert result.format_id is None
    assert "doesn't match" in result.checks[0].message


def test_validate_file_survives_a_corrupt_file(tmp_path, print_fmt, pdf_deliverable):
    named = tmp_path / (pdf_deliverable["expected_stem"] + ".pdf")
    named.write_bytes(b"this is not a real pdf")

    result = validate_file(named, _job(print_fmt, pdf_deliverable))
    assert result.status == "fail"
    assert result.checks[0].id == "read"


def test_validate_file_routes_png(fixtures_dir, social_fmt, png_deliverable, tmp_path):
    named = tmp_path / (png_deliverable["expected_stem"] + ".png")
    shutil.copyfile(fixtures_dir / "good_ig_post.png", named)

    result = validate_file(named, _job(social_fmt, png_deliverable))
    assert result.status == "ok"
