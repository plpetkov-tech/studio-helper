"""TIFF validator (SPEC.md §6.7)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import match
from .model import Check

MM_PER_IN = 25.4
PIXEL_TOLERANCE = 2


def validate(path: Path, fmt: dict, deliverable: dict) -> list[Check]:
    checks: list[Check] = []
    with Image.open(path) as img:
        checks.append(_check_mode(img))
        checks.append(_check_dimensions(img, fmt, deliverable))
        checks.append(_check_dpi_tag(img))
    return checks


def _check_mode(img: Image.Image) -> Check:
    if img.mode != "CMYK":
        return Check(
            "color-mode",
            "fail",
            f"This TIFF is {img.mode}; it should be CMYK.",
            "Export with imageColorSpace set to CMYK.",
        )
    return Check("color-mode", "ok", "CMYK, as expected.")


def _check_dimensions(img: Image.Image, fmt: dict, deliverable: dict) -> Check:
    w_mm, h_mm = match.deliverable_size(fmt, deliverable)
    bleed_mm = fmt.get("bleed_mm", 0) or 0
    tiff_ppi = fmt.get("tiff_ppi")
    scale = fmt.get("scale", 1) or 1

    if not tiff_ppi:
        return Check("dimensions", "ok", "No TIFF resolution configured to check against.")

    # The .ai is drawn at `scale` (bleed in its own mm, unscaled) and
    # exported at tiff_ppi / scale, i.e. tiff_ppi at the physical size.
    effective_ppi = tiff_ppi / scale
    expected_w = round((w_mm * scale + 2 * bleed_mm) / MM_PER_IN * effective_ppi)
    expected_h = round((h_mm * scale + 2 * bleed_mm) / MM_PER_IN * effective_ppi)
    actual_w, actual_h = img.size

    if abs(actual_w - expected_w) > PIXEL_TOLERANCE or abs(actual_h - expected_h) > PIXEL_TOLERANCE:
        return Check(
            "dimensions",
            "fail",
            f"This TIFF is {actual_w}×{actual_h}px; expected {expected_w}×{expected_h}px "
            f"(size + bleed at {tiff_ppi}ppi).",
            "Re-export at the size and resolution set for this format.",
        )
    return Check("dimensions", "ok", "Pixel dimensions match size + bleed at the expected ppi.")


def _check_dpi_tag(img: Image.Image) -> Check:
    if not img.info.get("dpi"):
        return Check(
            "dpi-tag",
            "fail",
            "This TIFF has no resolution (DPI) tag.",
            "Export with a resolution set, not just a pixel size.",
        )
    return Check("dpi-tag", "ok", "Resolution tag present.")
