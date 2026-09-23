"""High-level Illustrator operations (SPEC.md §6.3, §6.4).

Thin: this module only locates the right JSX file and shapes
arguments/results. All business logic (grouping by bleed, artboard
layout, naming) lives in the JSX itself, per SPEC.md §4's design
principle that Python is the brain and the JSX adapters are thin --
Illustrator geometry is the one exception, since it can only happen
inside Illustrator.
"""

from __future__ import annotations

from pathlib import Path

from studio_helper.adobe import bridge

PROGID = "Illustrator.Application"

ADOBE_ROOT = Path(__file__).resolve().parents[3] / "adobe" / "illustrator"
NEW_PRINT_DOC_JSX = ADOBE_ROOT / "new_print_doc.jsx"
INSPECT_JSX = ADOBE_ROOT / "inspect.jsx"
PREFLIGHT_EXPORT_JSX = ADOBE_ROOT / "preflight_export.jsx"


def is_running() -> bool:
    return bridge.is_running(PROGID)


def create_print_doc(job: dict, output_dir: Path) -> dict:
    app = bridge.connect(PROGID)
    return bridge.run_jsx(app, NEW_PRINT_DOC_JSX, {"job": job, "output_dir": str(output_dir)})


def inspect(ai_path: Path | None = None) -> dict:
    app = bridge.connect(PROGID)
    args = {"ai_path": str(ai_path)} if ai_path is not None else {}
    return bridge.run_jsx(app, INSPECT_JSX, args)


def preflight(
    job: dict,
    ai_path: Path,
    mode: str,
    export_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Runs preflight_export.jsx (SPEC.md §6.4): checks always run;
    `mode="export"` also exports every artboard to PDF or TIFF
    (by physical size) when there are no fail results, or `force`."""
    app = bridge.connect(PROGID)
    args: dict = {"job": job, "ai_path": str(ai_path), "mode": mode, "force": force}
    if export_dir is not None:
        args["export_dir"] = str(export_dir)
    return bridge.run_jsx(app, PREFLIGHT_EXPORT_JSX, args)


def pdf_preset_available(preset_name: str) -> bool:
    """Used by the Setup check: is the studio's PDF preset installed
    and visible to Illustrator? Connects (and may launch Illustrator)
    -- only called when she explicitly runs the Setup check, never on
    a passive page load."""
    result = inspect()
    presets = result.get("data", {}).get("pdf_presets", [])
    return preset_name in presets
