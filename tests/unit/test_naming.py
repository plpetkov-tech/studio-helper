from studio_helper.core import naming


def test_bulgarian_cyrillic_transliteration_matches_spec_example():
    # SPEC.md §6.1 naming: "Есенна разпродажба" -> "esenna-razprodazhba"
    assert naming.slugify("Есенна разпродажба") == "esenna-razprodazhba"


def test_ascii_name_kebab_cased():
    assert naming.slugify("Autumn Sale!!") == "autumn-sale"


def test_collapses_repeated_separators():
    assert naming.slugify("  multiple   spaces  ") == "multiple-spaces"


def test_strips_leading_trailing_punctuation():
    assert naming.slugify("--weird--") == "weird"


def test_truncates_to_max_length():
    long_name = "a" * 60
    slug = naming.slugify(long_name)
    assert len(slug) == naming.MAX_SLUG_LENGTH


def test_truncation_does_not_leave_trailing_hyphen():
    name = "a" * 39 + " " + "b" * 10
    slug = naming.slugify(name)
    assert not slug.endswith("-")
    assert len(slug) <= naming.MAX_SLUG_LENGTH


def test_empty_name_falls_back_to_job():
    assert naming.slugify("!!!") == "job"


def test_expected_stem_matches_spec_example():
    stem = naming.expected_stem(
        "2026-09-25", "autumn-sale", "flyer-a5", 148, 210, "mm", version=1
    )
    assert stem == "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01"


def test_expected_stem_with_panel():
    stem = naming.expected_stem(
        "2026-09-25", "autumn-sale", "elevator-main", 900, 2100, "mm", version=1, panel=2
    )
    assert stem == "2026-09-25_autumn-sale_elevator-main_900x2100mm_p2_v01"


def test_expected_stem_zero_pads_version():
    stem = naming.expected_stem("2026-09-25", "x", "y", 1, 1, "px", version=12)
    assert stem.endswith("_v12")


def test_expected_stem_non_integer_dimension():
    stem = naming.expected_stem("2026-09-25", "x", "y", 148.5, 210, "mm", version=1)
    assert "148.5x210mm" in stem
