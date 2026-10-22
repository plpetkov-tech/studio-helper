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


def test_expected_stem_is_the_name_and_the_size():
    assert naming.expected_stem("autumn-sale", 148, 210, "mm") == "autumn-sale_148x210mm"


def test_expected_stem_with_panel():
    stem = naming.expected_stem("autumn-sale", 900, 2100, "mm", panel=2)
    assert stem == "autumn-sale_900x2100mm_p2"


def test_expected_stem_with_the_format_id_when_sizes_clash():
    stem = naming.expected_stem("autumn-sale", 1080, 1920, "px", format_id="fb-story")
    assert stem == "autumn-sale_fb-story_1080x1920px"


def test_expected_stem_non_integer_dimension():
    stem = naming.expected_stem("x", 148.5, 210, "mm")
    assert "148.5x210mm" in stem
