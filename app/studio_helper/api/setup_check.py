"""Setup check page (SPEC.md §5.3): confirms Illustrator is reachable,
the studio's PDF preset is installed, the jobs folder is writable, the
registry is valid, and warns about Windows blocking the extracted zip
(Mark-of-the-Web). Photoshop/Figma checks land with those milestones
(M5); their instructions are shown as static content for now.

Runs as a background task (SPEC.md §6.2) since the Illustrator check
may launch it, which can take up to two minutes (SPEC.md §6.3) --
only when she explicitly clicks "Run checks", never on page load.
"""

from __future__ import annotations

import sys

from studio_helper import paths
from studio_helper.adobe import bridge, illustrator
from studio_helper.core.registry import RegistryError, load_registry

from .dispatch import route
from .openers import open_path

PDF_PRESET_NAME = "StudioHelper_X1a"


def _ok(check_id: str, message: str) -> dict:
    return {"id": check_id, "ok": True, "message": message, "hint": ""}


def _fail(check_id: str, message: str, hint: str) -> dict:
    return {"id": check_id, "ok": False, "message": message, "hint": hint}


def _check_registry(ctx) -> dict:
    try:
        load_registry(ctx.registry_path)
        return _ok("registry", "Registry is valid.")
    except RegistryError as exc:
        return _fail("registry", str(exc), "Open the Registry page and fix registry.yaml.")


def _check_jobs_folder(ctx) -> dict:
    try:
        ctx.jobs_root.mkdir(parents=True, exist_ok=True)
        probe = ctx.jobs_root / ".studio_helper_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return _ok("jobs_folder", f"{ctx.jobs_root} is writable.")
    except OSError as exc:
        return _fail(
            "jobs_folder",
            f"Can't write to {ctx.jobs_root}: {exc}",
            "Choose a different jobs folder, or fix its permissions.",
        )


def _check_illustrator_and_preset() -> tuple[dict, dict]:
    try:
        result = illustrator.inspect()
    except bridge.AdobeBridgeError as exc:
        illustrator_check = _fail(
            "illustrator",
            str(exc),
            "Make sure Illustrator is installed. You can still use the manual "
            "File > Scripts path shown on the Job page.",
        )
        preset_check = _fail(
            "pdf_preset",
            "Could not check -- Illustrator isn't reachable.",
            "",
        )
        return illustrator_check, preset_check

    illustrator_check = _ok("illustrator", "Illustrator is reachable.")
    presets = (result.get("data") or {}).get("pdf_presets", [])
    if PDF_PRESET_NAME in presets:
        preset_check = _ok("pdf_preset", f"'{PDF_PRESET_NAME}' preset is installed.")
    else:
        preset_check = _fail(
            "pdf_preset",
            f"'{PDF_PRESET_NAME}' preset was not found in Illustrator.",
            "This ships once the print department's exact PDF/X-1a settings are "
            "confirmed (see SPEC.md §13 open items).",
        )
    return illustrator_check, preset_check


def _check_mark_of_the_web() -> dict:
    if sys.platform != "win32":
        return _ok("mark_of_the_web", "Not applicable on this platform.")

    marker_file = paths.bundled_root() / "Start Studio Helper.bat"
    if not marker_file.exists():
        return _ok("mark_of_the_web", "Nothing to check in a dev checkout.")

    zone_identifier = marker_file.parent / (marker_file.name + ":Zone.Identifier")
    if zone_identifier.exists():
        return _fail(
            "mark_of_the_web",
            "Windows has flagged these files as downloaded from the internet.",
            "Right-click the zip, choose Properties, tick Unblock, then extract again.",
        )
    return _ok("mark_of_the_web", "Files are not blocked.")


def run_all_checks(ctx) -> dict:
    illustrator_check, preset_check = _check_illustrator_and_preset()
    checks = [
        _check_registry(ctx),
        _check_jobs_folder(ctx),
        illustrator_check,
        preset_check,
        _check_mark_of_the_web(),
    ]
    return {"checks": checks}


@route("POST", "/api/setup-check")
def start_setup_check(ctx, body):
    task_id = ctx.tasks.start(lambda: run_all_checks(ctx))
    return 200, {"ok": True, "task_id": task_id}


@route("POST", "/api/setup-check/open-figma-folder")
def open_figma_folder(ctx, body):
    open_path(paths.bundled_root() / "figma-plugin", reveal=True)
    return 200, {"ok": True}
