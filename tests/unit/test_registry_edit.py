import pytest
from studio_helper.core import registry_edit as re_
from studio_helper.core.registry import RegistryError

REG = """\
# her comment
version: 1
formats:
  # vinyl from IDEA
  - id: vinyl
    name: Vinyl   # mine
    kind: print
    size: {w: 4000, h: 3000, unit: mm}
    scale: 0.1
    exports: [tiff]

  - id: door
    name: Door
    kind: print
    panels:
      - {w: 900, h: 2100}
      - {w: 900, h: 2100}
    unit: mm
    notes: "old note"
    exports: [pdf]

job_types:
  all: [vinyl, door]
"""


def _file(tmp_path):
    p = tmp_path / "registry.yaml"
    p.write_text(REG, encoding="utf-8")
    return p


def test_update_changes_only_the_given_fields(tmp_path):
    p = _file(tmp_path)
    reg = re_.update_format(p, "vinyl", {
        "notes": "Pocket 7 cm: text 20 cm from edges", "bleed_mm": 0, "tiff_ppi": 60,
        "size": {"w": 4100, "h": 3100, "unit": "mm"}, "exports": ["tiff"],
    })
    f = reg.formats["vinyl"]
    assert f["notes"] == "Pocket 7 cm: text 20 cm from edges"
    assert (f["bleed_mm"], f["tiff_ppi"], f["size"]["w"]) == (0, 60, 4100)
    text = p.read_text(encoding="utf-8")
    assert "# her comment" in text and "# vinyl from IDEA" in text
    assert "name: Vinyl   # mine" in text
    assert reg.formats["door"]["notes"] == "old note"
    assert reg.job_types == {"all": ["vinyl", "door"]}


def test_update_removes_an_optional_field_and_keeps_panels(tmp_path):
    p = _file(tmp_path)
    reg = re_.update_format(p, "door", {"notes": "", "name": "Elevator door"})
    assert reg.formats["door"]["notes"] == ""  # default after removal
    assert "old note" not in p.read_text(encoding="utf-8")
    assert len(reg.formats["door"]["panels"]) == 2


def test_update_rejects_empty_required_and_restores_on_invalid(tmp_path):
    p = _file(tmp_path)
    with pytest.raises(re_.FormatEditError, match="name"):
        re_.update_format(p, "vinyl", {"name": ""})
    with pytest.raises(RegistryError):
        re_.update_format(p, "vinyl", {"exports": ["gif"]})
    assert p.read_text(encoding="utf-8") == REG


def test_delete_removes_the_entry_and_its_comment(tmp_path):
    p = _file(tmp_path)
    reg = re_.delete_format(p, "vinyl")
    assert list(reg.formats) == ["door"]
    text = p.read_text(encoding="utf-8")
    assert "vinyl from IDEA" not in text and "# her comment" in text


def test_unknown_format(tmp_path):
    with pytest.raises(re_.FormatEditError, match="No format"):
        re_.update_format(_file(tmp_path), "nope", {"notes": "x"})
