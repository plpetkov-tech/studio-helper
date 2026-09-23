"""Match an exported file to the job's deliverables by filename
(SPEC.md §6.7, §6.8)."""

from __future__ import annotations

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


def deliverable_size(fmt: dict, deliverable: dict) -> tuple[float, float]:
    """The physical size (mm for print, px for digital) this specific
    deliverable should be -- a panel's size if it's part of a
    multi-panel format, otherwise the format's own size."""
    if deliverable.get("panel") is not None:
        panel = fmt["panels"][deliverable["panel"] - 1]
        return panel["w"], panel["h"]
    return fmt["size"]["w"], fmt["size"]["h"]
