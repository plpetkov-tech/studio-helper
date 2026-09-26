from studio_helper.deliverables import collapse_alternatives


def _row(fid, typ, status, panel=None):
    return {"format_id": fid, "type": typ, "panel": panel, "status": status, "expected_stem": fid}


def test_one_row_per_digital_artboard_until_something_arrives():
    rows = [_row("flyer", "pdf", "missing"), _row("screen", "jpg", "missing"),
            _row("screen", "png", "missing")]
    out = collapse_alternatives(rows)
    assert [(r["format_id"], r["type"]) for r in out] == [("flyer", "pdf"), ("screen", "jpg")]
    assert out[1]["alternatives"] == ["png"]


def test_any_delivered_alternative_counts_and_hides_the_missing_one():
    rows = [_row("screen", "jpg", "missing"), _row("screen", "png", "ok")]
    assert collapse_alternatives(rows) == [rows[1]]


def test_print_rows_are_never_collapsed():
    rows = [_row("door", "pdf", "missing"), _row("door", "tiff", "missing")]
    assert collapse_alternatives(rows) == rows
