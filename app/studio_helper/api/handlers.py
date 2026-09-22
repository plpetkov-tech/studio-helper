"""API endpoint handlers for the Home / New Job / Job / Registry
screens (SPEC.md §6.2). Each handler returns (status, json-serializable
dict); the dispatcher (dispatch.py) turns domain errors into a 400
with a plain message.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.core.registry import Registry, load_registry

from .dispatch import route


def _load_registry(ctx) -> Registry:
    return load_registry(ctx.registry_path)


def _open_path(path: Path, *, reveal: bool) -> None:
    """`reveal=True` opens the containing app (Explorer/Finder/file
    manager) on a folder; `reveal=False` opens a file in the default
    text editor. Both are best-effort and never raise -- there is
    nothing useful the UI can do if the OS call itself fails."""
    try:
        if sys.platform == "win32":
            if reveal:
                subprocess.run(["explorer.exe", str(path)], check=False)
            else:
                subprocess.run(["notepad.exe", str(path)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open"] + ([] if reveal else ["-t"]) + [str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        pass


# -- config -----------------------------------------------------------


@route("GET", "/api/config")
def get_config(ctx, body):
    return 200, {
        "ok": True,
        "jobs_root": str(ctx.jobs_root),
        "registry_path": str(ctx.registry_path),
    }


# -- registry -----------------------------------------------------------


@route("GET", "/api/registry")
def get_registry(ctx, body):
    registry = _load_registry(ctx)
    return 200, {
        "ok": True,
        "version": registry.version,
        "print_defaults": registry.print_defaults,
        "formats": list(registry.formats.values()),
        "job_types": registry.job_types,
    }


@route("POST", "/api/registry/validate")
def validate_registry(ctx, body):
    _load_registry(ctx)
    return 200, {"ok": True, "message": "Registry is valid."}


@route("POST", "/api/registry/open")
def open_registry(ctx, body):
    _open_path(ctx.registry_path, reveal=False)
    return 200, {"ok": True}


# -- jobs -----------------------------------------------------------


@route("GET", "/api/jobs")
def list_jobs(ctx, body):
    jobs = job_mod.list_jobs(ctx.jobs_root)
    return 200, {"ok": True, "jobs": [_summarize(j, ctx.jobs_root) for j in jobs]}


@route("POST", "/api/jobs")
def create_job(ctx, body):
    body = body or {}
    registry = _load_registry(ctx)
    name = body.get("name", "")
    format_ids = body.get("format_ids")

    if format_ids is None:
        job_type = body.get("job_type")
        if not job_type:
            raise job_mod.JobError("Choose a job type or select formats.")
        format_ids = registry.resolve_job_type(job_type)

    job = job_mod.create_job(ctx.jobs_root, registry, name, format_ids)
    return 200, {"ok": True, "job": job}


@route("GET", "/api/jobs/<job_id>")
def get_job(ctx, body, job_id):
    job = job_mod.load_job(ctx.jobs_root, job_id)
    return 200, {"ok": True, "job": job, "deliverables": _deliverable_status(job, ctx.jobs_root)}


@route("POST", "/api/jobs/<job_id>/revision")
def start_revision(ctx, body, job_id):
    job = job_mod.bump_version(ctx.jobs_root, job_id)
    return 200, {"ok": True, "job": job}


@route("POST", "/api/jobs/<job_id>/open-folder")
def open_job_folder(ctx, body, job_id):
    root = job_mod.job_path(ctx.jobs_root, job_id)
    _open_path(root, reveal=True)
    return 200, {"ok": True}


# -- helpers -----------------------------------------------------------


def _summarize(job: dict, jobs_root: Path) -> dict:
    status = _deliverable_status(job, jobs_root)
    done = sum(1 for d in status if d["status"] == "found")
    return {
        "id": job["id"],
        "name": job["name"],
        "created": job["created"],
        "version": job["version"],
        "deliverables_done": done,
        "deliverables_total": len(status),
    }


def _deliverable_status(job: dict, jobs_root: Path) -> list[dict]:
    # A simple filename-stem match against 04_export/, good enough for
    # the Home/Job progress display until the real validators land
    # (SPEC.md M2) and start reporting pass/warn/fail per file.
    export_root = jobs_root / job["id"] / "04_export"
    stems_present: set[str] = set()
    if export_root.exists():
        for p in export_root.rglob("*"):
            if p.is_file():
                stems_present.add(p.stem)

    return [
        {**d, "status": "found" if d["expected_stem"] in stems_present else "missing"}
        for d in job["deliverables"]
    ]
