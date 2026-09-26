"""Match an exported file to the job's deliverables by filename
(SPEC.md §6.7, §6.8)."""

from __future__ import annotations

import math
from pathlib import Path

TYPE_EXTENSIONS = {
    "pdf": {".pdf"},
    "tiff": {".tif", ".tiff"},
    "png": {".png"},
    "jpg": {".jpg", ".jpeg"},
    "mp4": {".mp4"},
}


def match_deliverable(job: dict, filename: str) -> dict | None:
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()
    for deliverable in job.get("deliverables", []):
        if deliverable["expected_stem"] == stem and ext in TYPE_EXTENSIONS.get(
            deliverable["type"], ()
        ):
            return deliverable
    return None


def find_format(job: dict, format_id: str) -> dict | None:
    for fmt in job.get("formats", []):
        if fmt["id"] == format_id:
            return fmt
    return None


PT_PER_MM = 72 / 25.4


def doc_bleed_range_mm(fmt: dict) -> tuple[float, float]:
    """The bleed (mm, in the exported file's own scale) a correct export
    can have: exactly what the format asks for, up to that rounded up to
    whole points -- Illustrator stores bleed in whole points, so the
    scripts ask for the next point up (lib/common.jsx SH.bleedPt)."""
    exact = (fmt.get("bleed_mm", 0) or 0) * (fmt.get("scale", 1) or 1)
    if exact <= 0:
        return 0.0, 0.0
    rounded = math.ceil(exact * PT_PER_MM - 1e-6) / PT_PER_MM
    return exact, rounded


def deliverable_size(fmt: dict, deliverable: dict) -> tuple[float, float]:
    """The physical size (mm for print, px for digital) this specific
    deliverable should be -- a panel's size if it's part of a
    multi-panel format, otherwise the format's own size."""
    if deliverable.get("panel") is not None:
        panel = fmt["panels"][deliverable["panel"] - 1]
        return panel["w"], panel["h"]
    return fmt["size"]["w"], fmt["size"]["h"]
