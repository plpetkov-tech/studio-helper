"""High-level Photoshop operations (SPEC.md §6.3, §6.5).

Thin, same design as adobe/illustrator.py: locates the right JSX and
shapes arguments/results. All business logic (grid layout, per-
artboard export) lives in the JSX.
"""

from __future__ import annotations

from pathlib import Path

from studio_helper.adobe import bridge

PROGID = "Photoshop.Application"

ADOBE_ROOT = Path(__file__).resolve().parents[3] / "adobe" / "photoshop"
NEW_DIGITAL_DOC_JSX = ADOBE_ROOT / "new_digital_doc.jsx"
EXPORT_DIGITAL_JSX = ADOBE_ROOT / "export_digital.jsx"


def is_running() -> bool:
    return bridge.is_running(PROGID)


def create_digital_doc(job: dict, output_dir: Path) -> dict:
    app = bridge.connect(PROGID)
    return bridge.run_jsx(app, NEW_DIGITAL_DOC_JSX, {"job": job, "output_dir": str(output_dir)})


def export_digital(job: dict, psd_path: Path, export_dirs: dict[str, Path]) -> dict:
    """`export_dirs` maps a format kind ("screen"/"web"/"social") to
    the 04_export/<kind-dir> directory for it -- different digital
    formats in the same PSD can have different kinds (SPEC.md §6.1)."""
    app = bridge.connect(PROGID)
    args = {
        "job": job,
        "psd_path": str(psd_path),
        "export_dirs": {kind: str(path) for kind, path in export_dirs.items()},
    }
    return bridge.run_jsx(app, EXPORT_DIGITAL_JSX, args)
