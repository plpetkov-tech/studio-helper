from studio_helper.report import render_report, write_report
from studio_helper.validators.model import Check, FileResult

JOB = {
    "id": "2026-09-25_autumn-sale",
    "name": "Autumn Sale",
    "version": 1,
    "deliverables": [
        {
            "format_id": "flyer-a5", "type": "pdf", "panel": None,
            "expected_stem": "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01",
        },
        {
            "format_id": "ig-post", "type": "png", "panel": None,
            "expected_stem": "2026-09-25_autumn-sale_ig-post_1080x1350px_v01",
        },
    ],
}


def _ok_result(deliverable):
    return FileResult(
        path="/jobs/x/04_export/print/x.pdf",
        format_id=deliverable["format_id"],
        deliverable=deliverable,
        status="ok",
        checks=[Check("trimbox", "ok", "TrimBox matches.")],
    )


def _fail_result(deliverable):
    return FileResult(
        path="/jobs/x/04_export/print/x.pdf",
        format_id=deliverable["format_id"],
        deliverable=deliverable,
        status="fail",
        checks=[Check("bleed-coverage", "fail", "Missing bleed on the left edge.", "Extend it.")],
    )


def test_render_report_includes_job_name_and_counts():
    results = {"a": _ok_result(JOB["deliverables"][0])}
    html_out = render_report(JOB, results)
    assert "Autumn Sale" in html_out
    assert "1 / 2 deliverables ready" in html_out


def test_render_report_shows_missing_for_unmatched_deliverable():
    html_out = render_report(JOB, {})
    assert html_out.count("missing") >= 2  # badge class + label, for both deliverables


def test_render_report_includes_check_hint_on_failure():
    results = {"a": _fail_result(JOB["deliverables"][0])}
    html_out = render_report(JOB, results)
    assert "Missing bleed on the left edge." in html_out
    assert "Extend it." in html_out


def test_render_report_escapes_html_in_job_name():
    job = dict(JOB, name="<script>alert(1)</script>")
    html_out = render_report(job, {})
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_write_report_creates_file(tmp_path):
    job_dir = tmp_path / "2026-09-25_autumn-sale"
    job_dir.mkdir()
    path = write_report(job_dir, JOB, {})
    assert path == job_dir / "report.html"
    assert path.exists()
    assert "Autumn Sale" in path.read_text(encoding="utf-8")


def test_write_report_is_self_contained(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    path = write_report(job_dir, JOB, {})
    text = path.read_text(encoding="utf-8")
    assert "<link" not in text  # no external stylesheet
    assert "<script" not in text  # no external script
