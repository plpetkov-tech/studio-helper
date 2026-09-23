from studio_helper.validators.match import deliverable_size, find_format, match_deliverable

JOB = {
    "formats": [
        {"id": "flyer-a5", "kind": "print", "size": {"w": 148, "h": 210, "unit": "mm"}},
        {
            "id": "elevator-main",
            "kind": "print",
            "panels": [{"w": 900, "h": 2100}, {"w": 900, "h": 2100}],
            "unit": "mm",
        },
    ],
    "deliverables": [
        {
            "format_id": "flyer-a5", "type": "pdf", "panel": None,
            "expected_stem": "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01",
        },
        {
            "format_id": "elevator-main", "type": "pdf", "panel": 1,
            "expected_stem": "2026-09-25_autumn-sale_elevator-main_900x2100mm_p1_v01",
        },
    ],
}


def test_match_by_exact_stem_and_extension():
    d = match_deliverable(JOB, "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01.pdf")
    assert d is not None
    assert d["format_id"] == "flyer-a5"


def test_no_match_for_unrelated_filename():
    assert match_deliverable(JOB, "vacation_photo.jpg") is None


def test_no_match_when_extension_disagrees_with_type():
    # right stem, wrong extension for a "pdf" deliverable
    assert match_deliverable(JOB, "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01.png") is None


def test_jpg_matches_both_jpg_and_jpeg_extensions():
    job = {
        "deliverables": [
            {"format_id": "x", "type": "jpg", "panel": None, "expected_stem": "stem"},
        ]
    }
    assert match_deliverable(job, "stem.jpg") is not None
    assert match_deliverable(job, "stem.jpeg") is not None


def test_find_format_returns_none_when_missing():
    assert find_format(JOB, "does-not-exist") is None


def test_deliverable_size_uses_panel_when_present():
    fmt = find_format(JOB, "elevator-main")
    deliverable = JOB["deliverables"][1]
    assert deliverable_size(fmt, deliverable) == (900, 2100)


def test_deliverable_size_uses_format_size_when_no_panel():
    fmt = find_format(JOB, "flyer-a5")
    deliverable = JOB["deliverables"][0]
    assert deliverable_size(fmt, deliverable) == (148, 210)
