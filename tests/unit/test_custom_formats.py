import pytest
from studio_helper.core import custom_formats as cf
from studio_helper.core.registry import RegistryError, load_registry

REGISTRY = """\
# her own comment at the top
version: 1
print_defaults:
  bleed_mm: 3
  tiff_ppi: 150
formats:
  - id: flyer-a5
    name: A5 flyer
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]   # keep this comment

# presets she uses
job_types:
  flyers: [flyer-a5]
"""


def test_build_print_format():
    fmt = cf.build_format(
        {"name": "Mall of Sofia column wrap", "kind": "print", "w": "2400", "h": 1200,
         "bleed_mm": 20, "safe_mm": "", "export": "TIFF", "group": "Mall print",
         "notes": "Wraps a round column"},
        set(),
    )
    assert fmt == {
        "id": "mall-of-sofia-column-wrap", "name": "Mall of Sofia column wrap",
        "kind": "print", "group": "Mall print", "size": {"w": 2400, "h": 1200, "unit": "mm"},
        "bleed_mm": 20, "exports": ["tiff"], "notes": "Wraps a round column",
    }


def test_build_format_cyrillic_name_and_unique_id():
    fmt = cf.build_format({"name": "Витрина", "kind": "social", "w": 1080, "h": 1080,
                           "export": "png"}, {"vitrina"})
    assert fmt["id"] == "vitrina-2"
    assert fmt["size"]["unit"] == "px"


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"kind": "print", "w": 1, "h": 1}, "name"),
        ({"name": "x", "kind": "poster", "w": 1, "h": 1}, "print, a screen or social"),
        ({"name": "x", "kind": "print", "w": 0, "h": 1}, "w must be more than 0"),
        ({"name": "x", "kind": "print", "w": "abc", "h": 1}, "must be a number"),
        ({"name": "x", "kind": "social", "w": 1, "h": 1, "export": "tiff"}, "PNG or JPG"),
    ],
)
def test_build_format_rejects_bad_input(spec, message):
    with pytest.raises(cf.CustomFormatError, match=message):
        cf.build_format(spec, set())


def test_save_format_inserts_into_formats_and_keeps_comments(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY, encoding="utf-8")
    fmt = cf.build_format({"name": "Scroller", "kind": "print", "w": 3410, "h": 2430,
                           "export": "tiff", "notes": 'Text 10 cm from edges, "no EPS"'}, set())

    registry = cf.save_format(path, fmt)

    text = path.read_text(encoding="utf-8")
    assert "# her own comment at the top" in text
    assert "exports: [pdf]   # keep this comment" in text
    assert text.index("id: scroller") < text.index("# presets she uses")
    assert list(registry.formats) == ["flyer-a5", "scroller"]
    assert registry.formats["scroller"]["notes"] == 'Text 10 cm from edges, "no EPS"'
    assert registry.formats["scroller"]["tiff_ppi"] == 150  # print defaults apply
    assert registry.job_types == {"flyers": ["flyer-a5"]}


def test_save_format_when_formats_is_the_last_section(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY.split("\n# presets")[0] + "\n", encoding="utf-8")
    fmt = cf.build_format({"name": "Card", "kind": "print", "w": 90, "h": 50,
                           "export": "pdf"}, set())
    assert "card" in cf.save_format(path, fmt).formats


def test_save_format_restores_the_file_if_the_result_is_invalid(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(REGISTRY, encoding="utf-8")
    bad = {"id": "flyer-a5", "name": "dup", "kind": "print",
           "size": {"w": 1, "h": 1, "unit": "mm"}, "exports": ["pdf"]}
    with pytest.raises(RegistryError, match="Duplicate"):
        cf.save_format(path, bad)
    assert path.read_text(encoding="utf-8") == REGISTRY
    load_registry(path)
