from pathlib import Path

import pytest
from studio_helper.core import seeds
from studio_helper.core.registry import load_registry

DEFAULTS = load_registry(Path(__file__).parents[2] / "defaults" / "registry.yaml").formats


def f(fid, w, h, kind="screen", **extra):
    return {"id": fid, "kind": kind, "size": {"w": w, "h": h}, **extra}


@pytest.mark.parametrize("target,expected", [
    # a new Mall X CityLight starts from the Burgas Plaza CityLight
    ("mall-print-xo-park-raketa", "mall-print-burgas-plaza-citylight-1250"),
    # a 1:3 LED strip starts from the other 1:3 strip, not a story
    ("led-screen-3", "mall-screen-416x1248"),
    # the column (4:3) starts from the widest digital thing there is
    ("mall-screen-paradise-led-column", "web-1920x1080"),
])
def test_closest_source_on_her_real_formats(target, expected):
    pool = [DEFAULTS[i] for i in DEFAULTS if i != target]
    assert seeds.closest_source(DEFAULTS[target], pool)["id"] == expected


def test_print_and_digital_never_mix():
    target = f("new-print", 1000, 1000, kind="print")
    assert seeds.closest_source(target, [f("square-screen", 1080, 1080)]) is None


def test_tie_goes_to_the_larger_source():
    target = f("t", 500, 500)
    small, big = f("small", 100, 100), f("big", 2000, 2000)
    assert seeds.closest_source(target, [small, big])["id"] == "big"


def test_panel_formats_are_never_paired():
    panels = {"id": "pair", "kind": "print", "panels": [{"w": 1, "h": 1}], "unit": "mm"}
    assert seeds.closest_source(panels, [f("a", 1, 1, kind="print")]) is None
    assert seeds.closest_source(f("t", 1, 1, kind="print"), [panels]) is None


def test_seeds_for_pairs_only_new_sizes_with_old_ones():
    job = {"formats": [f("old-a", 1080, 1920), f("old-b", 1920, 1080),
                       f("new-tall", 1000, 1900), f("new-wide", 2000, 1000)]}
    assert seeds.seeds_for(job, ["new-tall", "new-wide"]) == [
        {"target": "new-tall", "source": "old-a"},
        {"target": "new-wide", "source": "old-b"},
    ]
