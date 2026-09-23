"""Validate an exported file against the job it belongs to (SPEC.md
§6.7). The exported file is the source of truth -- the same
validators run no matter which app produced it (SPEC.md §4).
"""

from __future__ import annotations

from pathlib import Path

from . import match, mp4, pdf, raster, tiff
from .model import Check, FileResult, overall_status

EXTENSION_VALIDATORS = {
    ".pdf": pdf.validate,
    ".tif": tiff.validate,
    ".tiff": tiff.validate,
    ".png": raster.validate,
    ".jpg": raster.validate,
    ".jpeg": raster.validate,
    ".mp4": mp4.validate,
}

__all__ = ["Check", "FileResult", "validate_file"]


def validate_file(path: Path, job: dict) -> FileResult:
    deliverable = match.match_deliverable(job, path.name)
    if deliverable is None:
        return FileResult(
            path=path,
            format_id=None,
            deliverable=None,
            status="warn",
            checks=[
                Check(
                    "filename",
                    "warn",
                    "File name doesn't match any deliverable of this job.",
                    "Rename it to match the expected name on the Job page, or remove it.",
                )
            ],
        )

    fmt = match.find_format(job, deliverable["format_id"])
    validator = EXTENSION_VALIDATORS.get(path.suffix.lower())

    if fmt is None or validator is None:
        checks = [
            Check(
                "filetype",
                "warn",
                f"Don't know how to check a '{path.suffix}' file.",
                "",
            )
        ]
    else:
        try:
            checks = validator(path, fmt, deliverable)
        except Exception as exc:  # noqa: BLE001 - a broken file must not crash the poller
            checks = [
                Check(
                    "read",
                    "fail",
                    f"Could not read this file: {exc}",
                    "Make sure the export finished and the file isn't open in another program.",
                )
            ]

    return FileResult(
        path=path,
        format_id=deliverable["format_id"],
        deliverable=deliverable,
        status=overall_status(checks),
        checks=checks,
    )
