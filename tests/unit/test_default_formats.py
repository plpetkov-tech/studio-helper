from pathlib import Path

from studio_helper.core import default_formats as df
from studio_helper.core.registry import load_registry

DEFAULTS = Path(__file__).parents[2] / "defaults" / "registry.yaml"

HERS = """\
version: 1
print_defaults:
  bleed_mm: 3
formats:
  - id: flyer-a5
    name: My A5   # her own edit
    kind: print
    size: {w: 148, h: 210, unit: mm}
    exports: [pdf]

job_types:
  mine: [flyer-a5]
"""


def test_default_entries_carry_their_comments():
    entries = df.default_entries(DEFAULTS.read_text(encoding="utf-8"))
    assert "banner-pair-stacked" in entries
    block = entries["banner-pair-stacked"]
    assert block.startswith("  # Two artboards of one composition")
    assert "panel_layout: column" in block
    assert "mall-screen" not in block


def test_first_merge_adds_only_new_defaults_and_keeps_her_file(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_text(HERS, encoding="utf-8")

    assert df.merge_new_defaults(user, DEFAULTS, seen) == ["banner-pair-stacked"]
    text = user.read_text(encoding="utf-8")
    assert "name: My A5   # her own edit" in text
    reg = load_registry(user)
    # old defaults she doesn't have stay out; only the new one comes in
    assert list(reg.formats) == ["flyer-a5", "banner-pair-stacked"]
    assert reg.formats["banner-pair-stacked"]["panel_layout"] == "column"
    assert reg.job_types == {"mine": ["flyer-a5"]}

    # nothing again on the next start, even after she deletes it
    user.write_text(HERS, encoding="utf-8")
    assert df.merge_new_defaults(user, DEFAULTS, seen) == []


def test_broken_registry_is_left_alone(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_text("version: 1\nformats: nope\n", encoding="utf-8")
    assert df.merge_new_defaults(user, DEFAULTS, seen) == []
    assert user.read_text(encoding="utf-8") == "version: 1\nformats: nope\n"
