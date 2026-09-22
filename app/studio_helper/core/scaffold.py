"""Job folder scaffold (SPEC.md §6.1)."""

from __future__ import annotations

from pathlib import Path

EXPORT_SUBDIR_BY_KIND = {
    "print": "print",
    "screen": "led",
    "web": "web",
    "social": "social",
}

SCAFFOLD_DIRS = [
    "01_brief",
    "02_assets",
    "03_working",
    "04_export/print",
    "04_export/led",
    "04_export/web",
    "04_export/social",
]


def create_job_folder(job_root: Path) -> None:
    """Creates the job's directory tree. Raises FileExistsError if
    job_root already exists -- callers pick a non-colliding id first."""
    job_root.mkdir(parents=True, exist_ok=False)
    for rel in SCAFFOLD_DIRS:
        (job_root / rel).mkdir(parents=True, exist_ok=True)
