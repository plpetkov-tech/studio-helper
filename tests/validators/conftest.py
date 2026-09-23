import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import make_fixtures  # noqa: E402


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("pdf_fixtures")
    make_fixtures.build_all(out)
    return out


@pytest.fixture()
def print_fmt() -> dict:
    return {
        "id": "flyer-a5",
        "name": "A5 flyer",
        "kind": "print",
        "size": {"w": 148, "h": 210, "unit": "mm"},
        "bleed_mm": 3,
        "safe_mm": 5,
        "exports": ["pdf", "tiff"],
        "min_image_ppi": {"warn": 300, "fail": 200},
        "tiff_if_longest_side_mm_over": 1000,
        "tiff_ppi": 150,
        "scale": 1,
        "allow_alpha": False,
    }


@pytest.fixture()
def pdf_deliverable() -> dict:
    return {
        "format_id": "flyer-a5",
        "type": "pdf",
        "panel": None,
        "expected_stem": "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01",
    }


@pytest.fixture()
def tiff_deliverable() -> dict:
    return {
        "format_id": "flyer-a5",
        "type": "tiff",
        "panel": None,
        "expected_stem": "2026-09-25_autumn-sale_flyer-a5_148x210mm_v01",
    }


@pytest.fixture()
def social_fmt() -> dict:
    return {
        "id": "ig-post",
        "name": "Instagram post",
        "kind": "social",
        "size": {"w": 1080, "h": 1350, "unit": "px"},
        "exports": ["png"],
        "allow_alpha": False,
        "scale": 1,
    }


@pytest.fixture()
def png_deliverable() -> dict:
    return {
        "format_id": "ig-post",
        "type": "png",
        "panel": None,
        "expected_stem": "2026-09-25_autumn-sale_ig-post_1080x1350px_v01",
    }


def status_of(checks, check_id: str) -> str | None:
    for c in checks:
        if c.id == check_id:
            return c.status
    return None
