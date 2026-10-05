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

    added = df.merge_new_defaults(user, DEFAULTS, seen)
    assert added[0] == "banner-pair-stacked"
    assert set(added[1:]) == {f for f in df.NEW_SINCE_FIRST_MERGE if f.startswith("web-")} | {
        "preset web"}
    text = user.read_text(encoding="utf-8")
    assert "name: My A5   # her own edit" in text
    reg = load_registry(user)
    # old defaults she doesn't have stay out; only the new ones come in
    assert list(reg.formats)[:2] == ["flyer-a5", "banner-pair-stacked"]
    assert "mall-print-paradise-snap-frame" not in reg.formats
    assert reg.formats["banner-pair-stacked"]["panel_layout"] == "column"
    assert reg.job_types == {"mine": ["flyer-a5"], "web": ["web-*"]}

    # nothing again on the next start, even after she deletes it
    user.write_text(HERS, encoding="utf-8")
    assert df.merge_new_defaults(user, DEFAULTS, seen) == []


def test_broken_registry_is_left_alone(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_text("version: 1\nformats: nope\n", encoding="utf-8")
    assert df.merge_new_defaults(user, DEFAULTS, seen) == []
    assert user.read_text(encoding="utf-8") == "version: 1\nformats: nope\n"


VINYL = """\
  - id: mall-print-idea-vinyl-4100x3100
    name: IDEA vinyl   # hers
    kind: print
    size: {w: 4100, h: 3100, unit: mm}
    scale: 0.1
    exports: [tiff]
"""


def _hers_with(entry):
    return HERS.replace("\njob_types:", "\n" + entry + "\njob_types:")


def test_tiff_patch_fills_her_vinyl_once(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_text(_hers_with(VINYL), encoding="utf-8")

    added = df.merge_new_defaults(user, DEFAULTS, seen)
    assert "mall-print-idea-vinyl-4100x3100.tiff_ppi" in added
    reg = load_registry(user)
    assert reg.formats["mall-print-idea-vinyl-4100x3100"]["tiff_ppi"] == 60
    assert "name: IDEA vinyl   # hers" in user.read_text(encoding="utf-8")

    # she changes it back by hand: the patch doesn't run again
    mine = VINYL.replace("    scale: 0.1\n", "    scale: 0.1\n    tiff_ppi: 100\n")
    user.write_text(_hers_with(mine), encoding="utf-8")
    df.merge_new_defaults(user, DEFAULTS, seen)
    assert load_registry(user).formats["mall-print-idea-vinyl-4100x3100"]["tiff_ppi"] == 100


def test_tiff_patch_never_overrides_her_own_value(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    mine = VINYL.replace("    kind: print\n", "    kind: print\n    tiff_ppi: 45\n")
    user.write_text(_hers_with(mine), encoding="utf-8")
    df.merge_new_defaults(user, DEFAULTS, seen)
    assert load_registry(user).formats["mall-print-idea-vinyl-4100x3100"]["tiff_ppi"] == 45


def test_new_web_formats_and_preset_reach_her_file(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_text(HERS, encoding="utf-8")
    added = df.merge_new_defaults(user, DEFAULTS, seen)
    reg = load_registry(user)
    assert "web-1920x1080" in reg.formats
    notes = reg.formats["web-1920x1080"]["notes"]
    assert notes == "For the website. No logo, with the campaign terms."
    assert "preset web" in added
    assert reg.job_types["web"] == ["web-*"]
    assert reg.job_types["mine"] == ["flyer-a5"]
    assert "mall-print" not in reg.job_types  # older presets she doesn't have stay out

    # she deletes the preset: it stays deleted
    user.write_text(user.read_text(encoding="utf-8").replace('  web: ["web-*"]\n', ""),
                    encoding="utf-8")
    df.merge_new_defaults(user, DEFAULTS, seen)
    assert "web" not in load_registry(user).job_types
