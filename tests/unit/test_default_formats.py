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
        "mall-screen-paradise-led-column", "preset web"}
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


SCREENS = """\
  - id: mall-print-idea-scroller-3410x2430
    name: IDEA Comm 9 m² scroller (3410 x 2430 mm, artwork at 1:10)
    kind: print
    size: {w: 3410, h: 2430, unit: mm}
    safe_mm: 100
    scale: 0.1
    exports: [tiff]

  - id: mall-screen-paradise-led-column-estimated
    name: Paradise Center LED column - estimated 4 mm pitch (960 x 720 px)
    kind: screen
    size: {w: 960, h: 720, unit: px}
    exports: [jpg, mp4]

  - id: mall-screen-veliko-turnovo-led
    name: Veliko Turnovo Mall LED screen (512 x 3968 px; reused for later listings)
    kind: screen
    size: {w: 512, h: 3968, unit: px}
    exports: [jpg, mp4]
    max_kb: 30720

  - id: led-screen-1
    name: LED Screen 1
    group: Screens
    kind: screen
    size: {w: 1600, h: 2560, unit: px}
    exports: [png]
"""


def test_her_october_registry_gets_real_screen_specs(tmp_path):
    # Shape of her registry backup from 2026-10: CRLF, older entries, her own LED screens.
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_bytes(_hers_with(SCREENS).replace("\n", "\r\n").encode("utf-8"))
    seen.write_text('["banner-pair-stacked"]', encoding="utf-8")

    added = df.merge_new_defaults(user, DEFAULTS, seen)
    reg = load_registry(user)
    column = reg.formats["mall-screen-paradise-led-column"]
    assert (column["size"]["w"], column["size"]["h"]) == (1920, 1440)
    assert column["exports"] == ["png", "mp4"]
    assert reg.formats["mall-print-idea-scroller-3410x2430"]["tiff_ppi"] == 30
    assert reg.formats["mall-screen-veliko-turnovo-led"]["notes"].startswith("Vertical.")
    assert "led-screen-1" not in added  # hers already
    # the estimate is swapped for the real spec in place, not listed twice
    assert "mall-screen-paradise-led-column-estimated" not in reg.formats
    ids = list(reg.formats)
    column, veliko = "mall-screen-paradise-led-column", "mall-screen-veliko-turnovo-led"
    assert ids.index(column) < ids.index(veliko)  # same place as the old entry
    assert user.read_bytes().count(b"mall-screen-paradise-led-column") == 1

    # nothing more on the next start
    assert df.merge_new_defaults(user, DEFAULTS, seen) == []


MALL_PRINT = """\
  - id: mall-print-burgas-galleria-poster
    name: Burgas Galleria corridor poster (500 x 700 mm)
    kind: print
    size: {w: 500, h: 700, unit: mm}
    exports: [pdf]

  - id: mall-print-plovdiv-entrance-door
    name: Plovdiv Mall entrance door
    kind: print
    size: {w: 1090, h: 2300, unit: mm}
    scale: 0.1
    exports: [pdf, tiff]

  - id: mall-print-xo-park-raketa
    name: XO Park Raketa   # she switched this one back herself
    kind: print
    size: {w: 1185, h: 1750, unit: mm}
    exports: [tiff, pdf]
"""


def test_her_old_pdf_mall_print_becomes_tiff_once(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    user.write_text(_hers_with(MALL_PRINT), encoding="utf-8")
    seen.write_text('["banner-pair-stacked"]', encoding="utf-8")

    added = df.merge_new_defaults(user, DEFAULTS, seen)
    reg = load_registry(user)
    assert reg.formats["mall-print-burgas-galleria-poster"]["exports"] == ["tiff"]
    assert reg.formats["mall-print-plovdiv-entrance-door"]["exports"] == ["tiff"]
    assert reg.formats["mall-print-xo-park-raketa"]["exports"] == ["tiff", "pdf"]  # not a default
    assert reg.formats["flyer-a5"]["exports"] == ["pdf"]  # small print stays PDF
    assert "mall-print-burgas-galleria-poster.exports" in added
    assert "name: XO Park Raketa   # she switched this one back herself" in user.read_text(
        encoding="utf-8")

    # she sets one back to PDF: it stays
    user.write_text(user.read_text(encoding="utf-8").replace(
        "size: {w: 500, h: 700, unit: mm}\n    exports: [tiff]",
        "size: {w: 500, h: 700, unit: mm}\n    exports: [pdf]"), encoding="utf-8")
    df.merge_new_defaults(user, DEFAULTS, seen)
    assert load_registry(user).formats["mall-print-burgas-galleria-poster"]["exports"] == ["pdf"]


def test_paradise_column_she_resized_herself_is_kept_and_not_duplicated(tmp_path):
    user, seen = tmp_path / "registry.yaml", tmp_path / "seen.json"
    mine = SCREENS.replace("{w: 960, h: 720, unit: px}", "{w: 1920, h: 1440, unit: px}")
    user.write_text(_hers_with(mine), encoding="utf-8")
    seen.write_text('["banner-pair-stacked"]', encoding="utf-8")

    df.merge_new_defaults(user, DEFAULTS, seen)
    reg = load_registry(user)
    assert reg.formats["mall-screen-paradise-led-column-estimated"]["size"]["w"] == 1920
    assert "mall-screen-paradise-led-column" not in reg.formats


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
