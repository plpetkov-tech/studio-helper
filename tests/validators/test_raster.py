from conftest import status_of
from studio_helper.validators import raster


def test_good_png_all_ok(fixtures_dir, social_fmt, png_deliverable):
    checks = raster.validate(fixtures_dir / "good_ig_post.png", social_fmt, png_deliverable)
    assert all(c.status == "ok" for c in checks), checks
    ids = {c.id for c in checks}
    assert ids == {"dimensions", "color-mode", "color-profile", "file-size"}


def test_wrong_dims_fail(fixtures_dir, social_fmt, png_deliverable):
    checks = raster.validate(fixtures_dir / "wrong_dims.png", social_fmt, png_deliverable)
    assert status_of(checks, "dimensions") == "fail"


def test_unwanted_alpha_fails_when_not_allowed(fixtures_dir, social_fmt, png_deliverable):
    checks = raster.validate(fixtures_dir / "unwanted_alpha.png", social_fmt, png_deliverable)
    assert status_of(checks, "color-mode") == "fail"


def test_alpha_ok_when_format_allows_it(fixtures_dir, social_fmt, png_deliverable):
    fmt = dict(social_fmt, allow_alpha=True)
    checks = raster.validate(fixtures_dir / "unwanted_alpha.png", fmt, png_deliverable)
    assert status_of(checks, "color-mode") == "ok"


def test_max_kb_warns_when_exceeded(fixtures_dir, social_fmt, png_deliverable):
    fmt = dict(social_fmt, max_kb=1)  # good_ig_post.png is comfortably bigger than 1KB
    checks = raster.validate(fixtures_dir / "good_ig_post.png", fmt, png_deliverable)
    assert status_of(checks, "file-size") == "warn"
