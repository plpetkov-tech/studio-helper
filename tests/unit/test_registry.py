import pytest
from studio_helper.core.registry import RegistryError, load_registry

GOOD = """\
version: 1
print_defaults:
  bleed_mm: 3
  safe_mm: 5
  pdf_preset: StudioHelper_X1a
  raster_ppi: 300
  min_image_ppi: {warn: 300, fail: 200}
  tiff_if_longest_side_mm_over: 1000
  tiff_ppi: 150
formats:
  - id: flyer-a5
    name: A5 flyer
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]
  - id: led-mall-entrance
    name: LED mall entrance
    kind: screen
    size: {w: 384, h: 1920, unit: px}
    exports: [png, mp4]
    allow_alpha: false
  - id: elevator-main
    name: Elevator doors
    kind: print
    panels:
      - {w: 900, h: 2100}
      - {w: 900, h: 2100}
    panel_gap_mm: 20
    unit: mm
    exports: [pdf]
job_types:
  full-campaign: [flyer-a4, flyer-a5, flyer-a6, "led-*"]
  shop-promo: [flyer-a4, "led-*"]
"""


def test_loads_default_registry_from_repo():
    from studio_helper import paths

    registry = load_registry(paths.bundled_registry_path())
    assert registry.version == 1
    assert "flyer-a5" in registry.formats


def test_valid_registry_loads(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(GOOD, encoding="utf-8")
    registry = load_registry(path)
    assert registry.version == 1
    assert set(registry.formats) == {"flyer-a5", "led-mall-entrance", "elevator-main"}


def test_print_format_inherits_print_defaults(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(GOOD, encoding="utf-8")
    registry = load_registry(path)
    flyer = registry.formats["flyer-a5"]
    assert flyer["bleed_mm"] == 3
    assert flyer["safe_mm"] == 5
    assert flyer["pdf_preset"] == "StudioHelper_X1a"


def test_screen_format_has_no_bleed(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(GOOD, encoding="utf-8")
    registry = load_registry(path)
    led = registry.formats["led-mall-entrance"]
    assert "bleed_mm" not in led


def test_defaults_applied(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(GOOD, encoding="utf-8")
    registry = load_registry(path)
    assert registry.formats["flyer-a5"]["scale"] == 1
    assert registry.formats["flyer-a5"]["allow_alpha"] is False


def test_missing_file_raises_with_path(tmp_path):
    with pytest.raises(RegistryError) as exc_info:
        load_registry(tmp_path / "nope.yaml")
    assert "nope.yaml" in str(exc_info.value)


def test_empty_file_raises(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path)


def test_unknown_top_level_key_reports_file_and_line(tmp_path):
    text = (
        "version: 1\n"
        "mystery_field: 42\n"
        "formats:\n"
        "  - id: a\n"
        "    name: A\n"
        "    kind: print\n"
        "    size: {w: 1, h: 1, unit: mm}\n"
        "    exports: [pdf]\n"
    )
    path = tmp_path / "registry.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RegistryError) as exc_info:
        load_registry(path)
    err = exc_info.value
    assert err.registry_path == path
    assert err.line == 2  # the "mystery_field: 42" line


def test_unknown_format_key_reports_line(tmp_path):
    text = (
        "version: 1\n"
        "formats:\n"
        "  - id: a\n"
        "    name: A\n"
        "    kind: print\n"
        "    size: {w: 1, h: 1, unit: mm}\n"
        "    exports: [pdf]\n"
        "    bogus_key: true\n"
    )
    path = tmp_path / "registry.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RegistryError) as exc_info:
        load_registry(path)
    assert exc_info.value.line == 8


def test_duplicate_format_id_rejected(tmp_path):
    text = (
        "version: 1\n"
        "formats:\n"
        "  - id: a\n"
        "    name: A\n"
        "    kind: print\n"
        "    size: {w: 1, h: 1, unit: mm}\n"
        "    exports: [pdf]\n"
        "  - id: a\n"
        "    name: A2\n"
        "    kind: print\n"
        "    size: {w: 2, h: 2, unit: mm}\n"
        "    exports: [pdf]\n"
    )
    path = tmp_path / "registry.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RegistryError, match="Duplicate format id 'a'"):
        load_registry(path)


def test_format_missing_size_and_panels_rejected(tmp_path):
    text = (
        "version: 1\n"
        "formats:\n"
        "  - id: a\n"
        "    name: A\n"
        "    kind: print\n"
        "    exports: [pdf]\n"
    )
    path = tmp_path / "registry.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path)


def test_invalid_kind_rejected(tmp_path):
    text = (
        "version: 1\n"
        "formats:\n"
        "  - id: a\n"
        "    name: A\n"
        "    kind: nonsense\n"
        "    size: {w: 1, h: 1, unit: mm}\n"
        "    exports: [pdf]\n"
    )
    path = tmp_path / "registry.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path)


def test_malformed_yaml_raises_registry_error(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text("version: 1\nformats: [\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(path)


def test_resolve_job_type_expands_globs(tmp_path):
    path = tmp_path / "registry.yaml"
    text = (
        "version: 1\n"
        "formats:\n"
        "  - id: led-a\n"
        "    name: LED A\n"
        "    kind: screen\n"
        "    size: {w: 1, h: 1, unit: px}\n"
        "    exports: [png]\n"
        "  - id: led-b\n"
        "    name: LED B\n"
        "    kind: screen\n"
        "    size: {w: 1, h: 1, unit: px}\n"
        "    exports: [png]\n"
        "  - id: flyer-a4\n"
        "    name: A4 flyer\n"
        "    kind: print\n"
        "    size: {w: 210, h: 297, unit: mm}\n"
        "    exports: [pdf]\n"
        "job_types:\n"
        "  full-campaign: [flyer-a4, \"led-*\"]\n"
    )
    path.write_text(text, encoding="utf-8")
    registry = load_registry(path)
    resolved = registry.resolve_job_type("full-campaign")
    assert set(resolved) == {"flyer-a4", "led-a", "led-b"}


def test_resolve_unknown_job_type_raises(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(GOOD, encoding="utf-8")
    registry = load_registry(path)
    with pytest.raises(RegistryError, match="Unknown job type"):
        registry.resolve_job_type("does-not-exist")
