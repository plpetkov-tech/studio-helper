"""Job creation and lifecycle (SPEC.md §6.1). Python is the sole
writer of job.json -- the JSX/Figma adapters only ever receive it and
report results back (SPEC.md §4 design principles)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from studio_helper import paths
from studio_helper.core import naming, scaffold
from studio_helper.core.registry import Registry

SCHEMA_VERSION = 1


class JobError(Exception):
    pass


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _deliverables_for(date_str: str, slug: str, fmt: dict, version: int) -> list[dict]:
    exports = fmt.get("exports", [])
    panels = fmt.get("panels")
    unit = fmt.get("unit") or fmt["size"]["unit"]
    deliverables = []

    def add(w: float, h: float, panel_index: int | None) -> None:
        for export_type in exports:
            deliverables.append(
                {
                    "format_id": fmt["id"],
                    "type": export_type,
                    "panel": panel_index,
                    "expected_stem": naming.expected_stem(
                        date_str, slug, fmt["id"], w, h, unit, version, panel_index
                    ),
                }
            )

    if panels:
        for i, p in enumerate(panels, start=1):
            add(p["w"], p["h"], i)
    else:
        add(fmt["size"]["w"], fmt["size"]["h"], None)

    return deliverables


# Illustrator's canvas is 5765mm (227in) per side; its new_print_doc.jsx
# also keeps a margin for bleed. Anything bigger is drawn at 1:10.
ILLUSTRATOR_MAX_ARTBOARD_MM = 5500


def _auto_scale(fmt: dict) -> dict:
    """Print formats too big for an Illustrator artboard at 1:1 get
    `scale: 0.1` (SPEC.md §6.4 "Scale"). A scale the registry already
    set to something other than 1 is kept as is."""
    if fmt["kind"] != "print" or fmt.get("scale", 1) != 1:
        return fmt
    sides = [(p["w"], p["h"]) for p in fmt["panels"]] if fmt.get("panels") else [
        (fmt["size"]["w"], fmt["size"]["h"])
    ]
    if max(max(w, h) for w, h in sides) > ILLUSTRATOR_MAX_ARTBOARD_MM:
        fmt["scale"] = 0.1
    return fmt


def auto_scale_job(jobs_root: Path, job_id: str) -> dict:
    """Applies _auto_scale to a job created before it existed, so its
    oversize print formats work without recreating the job. Expected
    file names don't depend on scale, so deliverables stay as they are."""
    job = load_job(jobs_root, job_id)
    before = [f.get("scale", 1) for f in job["formats"]]
    job["formats"] = [_auto_scale(f) for f in job["formats"]]
    if [f.get("scale", 1) for f in job["formats"]] != before:
        _write_job(job_path(jobs_root, job_id), job)
    return job


def create_job(
    jobs_root: Path,
    registry: Registry,
    name: str,
    format_ids: list[str],
    now: datetime | None = None,
) -> dict:
    if not name or not name.strip():
        raise JobError("Job name cannot be empty.")
    if not format_ids:
        raise JobError("Select at least one format.")

    unknown = [fid for fid in format_ids if fid not in registry.formats]
    if unknown:
        raise JobError(f"Unknown format id(s): {', '.join(unknown)}")

    now = now or _now_local()
    date_str = now.strftime("%Y-%m-%d")
    base_slug = naming.slugify(name)

    slug = base_slug
    job_id = f"{date_str}_{slug}"
    job_root = jobs_root / job_id
    suffix = 2
    while job_root.exists():
        slug = f"{base_slug}-{suffix}"
        job_id = f"{date_str}_{slug}"
        job_root = jobs_root / job_id
        suffix += 1

    if not paths.is_inside(job_root, jobs_root):
        raise JobError("Refusing to create a job outside the jobs folder.")

    scaffold.create_job_folder(job_root)

    version = 1
    # Fully resolved copies (incl. defaults) so the job stays stable
    # even if registry.yaml changes later (SPEC.md §6.1 job.json).
    formats_resolved = [_auto_scale(dict(registry.formats[fid])) for fid in format_ids]
    deliverables = []
    for fmt in formats_resolved:
        deliverables.extend(_deliverables_for(date_str, slug, fmt, version))

    job = {
        "schema_version": SCHEMA_VERSION,
        "id": job_id,
        "name": name.strip(),
        "slug": slug,
        "created": now.isoformat(timespec="seconds"),
        "registry_version": registry.version,
        "version": version,
        "formats": formats_resolved,
        "files": {"print": [], "psd": None},
        "deliverables": deliverables,
    }

    _write_job(job_root, job)
    return job


def _write_job(job_root: Path, job: dict) -> None:
    (job_root / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def job_path(jobs_root: Path, job_id: str) -> Path:
    candidate = jobs_root / job_id
    if not paths.is_inside(candidate, jobs_root):
        raise JobError("Invalid job id.")
    return candidate


def load_job(jobs_root: Path, job_id: str) -> dict:
    root = job_path(jobs_root, job_id)
    job_file = root / "job.json"
    if not job_file.exists():
        raise JobError(f"No such job: {job_id}")
    return json.loads(job_file.read_text(encoding="utf-8"))


def list_jobs(jobs_root: Path) -> list[dict]:
    if not jobs_root.exists():
        return []
    jobs = []
    for child in sorted(jobs_root.iterdir(), reverse=True):
        job_file = child / "job.json"
        if child.is_dir() and job_file.exists():
            try:
                jobs.append(json.loads(job_file.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return jobs


def record_print_files(jobs_root: Path, job_id: str, ai_paths: list[str]) -> dict:
    """Records .ai files created by the Illustrator adapter in
    job.json's files.print list, as paths relative to the job root
    (SPEC.md §6.1 job.json example: "03_working/..._print_v01.ai").
    Python remains the sole writer of job.json (SPEC.md §4)."""
    root = job_path(jobs_root, job_id)
    job = load_job(jobs_root, job_id)
    existing = job["files"].get("print") or []

    for raw_path in ai_paths:
        p = Path(raw_path)
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.as_posix()
        if rel not in existing:
            existing.append(rel)

    job["files"]["print"] = existing
    _write_job(root, job)
    return job


def record_digital_file(jobs_root: Path, job_id: str, psd_path: str) -> dict:
    """Records the .psd file created by the Photoshop adapter in
    job.json's files.psd (a single path, unlike files.print -- one PSD
    holds every digital format, per SPEC.md §6.5)."""
    root = job_path(jobs_root, job_id)
    job = load_job(jobs_root, job_id)

    p = Path(psd_path)
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        rel = p.as_posix()

    job["files"]["psd"] = rel
    _write_job(root, job)
    return job


DELETED_JOBS_DIR = "_Deleted Jobs"


def delete_job(jobs_root: Path, job_id: str) -> Path:
    """Move the job folder into `_Deleted Jobs/` under jobs_root. Never
    erases anything: her .ai/.psd files must survive (SPEC.md §2 point 6),
    so a deleted job can be restored by moving the folder back."""
    root = job_path(jobs_root, job_id)
    if not (root / "job.json").exists():
        raise JobError(f"No such job: {job_id}")

    trash = jobs_root / DELETED_JOBS_DIR
    trash.mkdir(exist_ok=True)
    dest = trash / job_id
    n = 2
    while dest.exists():
        dest = trash / f"{job_id} ({n})"
        n += 1
    try:
        root.rename(dest)
    except PermissionError as exc:
        raise JobError(
            "Could not delete the job -- a file in it is open. "
            "Close it in Illustrator/Photoshop and try again."
        ) from exc
    return dest


def bump_version(jobs_root: Path, job_id: str) -> dict:
    """'Start revision': vN -> vN+1. New exports get the new version;
    older files are left in place (SPEC.md §6.1 naming)."""
    job = load_job(jobs_root, job_id)
    job["version"] += 1
    date_str = datetime.fromisoformat(job["created"]).strftime("%Y-%m-%d")

    deliverables = []
    for fmt in job["formats"]:
        deliverables.extend(_deliverables_for(date_str, job["slug"], fmt, job["version"]))
    job["deliverables"] = deliverables

    _write_job(job_path(jobs_root, job_id), job)
    return job
