"""API endpoint handlers for the Home / New Job / Job / Registry
screens (SPEC.md §6.2). Each handler returns (status, json-serializable
dict); the dispatcher (dispatch.py) turns domain errors into a 400
with a plain message.
"""

from __future__ import annotations

from pathlib import Path

from studio_helper import paths as app_paths
from studio_helper.adobe import illustrator, photoshop
from studio_helper.core import custom_formats
from studio_helper.core import job as job_mod
from studio_helper.core.registry import Registry, load_registry
from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND
from studio_helper.deliverables import collapse_alternatives, deliverables_table

from .dispatch import route
from .openers import open_path


def _load_registry(ctx) -> Registry:
    return load_registry(ctx.registry_path)


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
        "groups": registry.groups,
        "job_types": registry.job_types,
    }


@route("POST", "/api/registry/formats")
def add_format(ctx, body):
    """"+ Add format" on the Formats page: saves straight to registry.yaml."""
    registry = _load_registry(ctx)
    fmt = _build_custom(body or {}, registry)
    registry = custom_formats.save_format(ctx.registry_path, fmt)
    return 200, {"ok": True, "format": registry.formats[fmt["id"]]}


def _build_custom(spec: dict, registry: Registry, taken: set[str] | None = None) -> dict:
    try:
        return custom_formats.build_format(spec, set(registry.formats) | (taken or set()))
    except custom_formats.CustomFormatError as exc:
        raise job_mod.JobError(str(exc)) from exc


@route("POST", "/api/registry/validate")
def validate_registry(ctx, body):
    _load_registry(ctx)
    return 200, {"ok": True, "message": "Registry is valid."}


@route("POST", "/api/registry/open")
def open_registry(ctx, body):
    open_path(ctx.registry_path, reveal=False)
    return 200, {"ok": True}


# -- jobs -----------------------------------------------------------


@route("GET", "/api/jobs")
def list_jobs(ctx, body):
    jobs = job_mod.list_jobs(ctx.jobs_root)
    return 200, {"ok": True, "jobs": [_summarize(j, ctx) for j in jobs]}


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
    format_ids = list(format_ids)
    if not str(name).strip():
        raise job_mod.JobError("Job name cannot be empty.")

    # "Custom size" entries: validate them all before saving any, so a
    # typo in the second one doesn't leave the first half-saved.
    specs = body.get("custom_formats") or []
    built, taken = [], set()
    for spec in specs:
        fmt = _build_custom(spec, registry, taken)
        taken.add(fmt["id"])
        built.append((spec, fmt))
    one_off = []
    for spec, fmt in built:
        if spec.get("save"):
            registry = custom_formats.save_format(ctx.registry_path, fmt)
            format_ids.append(fmt["id"])
        else:
            one_off.append(custom_formats.resolve_custom(fmt, registry))

    job = job_mod.create_job(
        ctx.jobs_root, registry, name, format_ids,
        bleed_overrides=body.get("bleed_overrides") or {},
        custom_formats=one_off,
    )
    return 200, {"ok": True, "job": job}


@route("GET", "/api/jobs/<job_id>")
def get_job(ctx, body, job_id):
    job = job_mod.load_job(ctx.jobs_root, job_id)
    return 200, {"ok": True, "job": job, "deliverables": _deliverable_status(job, ctx)}


@route("POST", "/api/jobs/<job_id>/revision")
def start_revision(ctx, body, job_id):
    job = job_mod.bump_version(ctx.jobs_root, job_id)
    return 200, {"ok": True, "job": job}


@route("POST", "/api/jobs/<job_id>/delete")
def delete_job(ctx, body, job_id):
    dest = job_mod.delete_job(ctx.jobs_root, job_id)
    return 200, {"ok": True, "moved_to": str(dest)}


@route("POST", "/api/jobs/<job_id>/open-folder")
def open_job_folder(ctx, body, job_id):
    root = job_mod.job_path(ctx.jobs_root, job_id)
    open_path(root, reveal=True)
    return 200, {"ok": True}


@route("POST", "/api/jobs/<job_id>/illustrator/new-print-doc")
def create_illustrator_print_doc(ctx, body, job_id):
    job = job_mod.auto_scale_job(ctx.jobs_root, job_id)
    working_dir = job_mod.job_path(ctx.jobs_root, job_id) / "03_working"

    def work() -> dict:
        result = illustrator.create_print_doc(job, working_dir)
        if result.get("ok"):
            paths = [d["path"] for d in result.get("data", {}).get("documents", [])]
            job_mod.record_print_files(ctx.jobs_root, job_id, paths)
        return result

    task_id = ctx.tasks.start(work)
    return 200, {"ok": True, "task_id": task_id}


@route("POST", "/api/jobs/<job_id>/illustrator/check-print")
def check_illustrator_print(ctx, body, job_id):
    job = job_mod.load_job(ctx.jobs_root, job_id)
    ai_paths = _print_ai_paths(ctx, job)
    if not ai_paths:
        raise job_mod.JobError(
            "No Illustrator print file yet -- click \"Create Illustrator print file\" first."
        )

    def work() -> dict:
        return {
            "files": [
                {"ai_path": str(p), "result": illustrator.preflight(job, p, mode="check")}
                for p in ai_paths
            ]
        }

    task_id = ctx.tasks.start(work)
    return 200, {"ok": True, "task_id": task_id}


@route("POST", "/api/jobs/<job_id>/illustrator/export-print")
def export_illustrator_print(ctx, body, job_id):
    body = body or {}
    force = bool(body.get("force"))
    only_ai_path = body.get("ai_path")  # scopes an "export anyway" retry to one file

    job = job_mod.load_job(ctx.jobs_root, job_id)
    ai_paths = _print_ai_paths(ctx, job)
    if not ai_paths:
        raise job_mod.JobError(
            "No Illustrator print file yet -- click \"Create Illustrator print file\" first."
        )
    if only_ai_path:
        ai_paths = [p for p in ai_paths if str(p) == only_ai_path]

    export_dir = job_mod.job_path(ctx.jobs_root, job_id) / "04_export" / "print"

    def work() -> dict:
        return {
            "files": [
                {
                    "ai_path": str(p),
                    "result": illustrator.preflight(
                        job, p, mode="export", export_dir=export_dir, force=force
                    ),
                }
                for p in ai_paths
            ]
        }

    task_id = ctx.tasks.start(work)
    return 200, {"ok": True, "task_id": task_id}


@route("POST", "/api/jobs/<job_id>/photoshop/new-digital-doc")
def create_photoshop_digital_doc(ctx, body, job_id):
    job = job_mod.load_job(ctx.jobs_root, job_id)
    working_dir = job_mod.job_path(ctx.jobs_root, job_id) / "03_working"

    def work() -> dict:
        result = photoshop.create_digital_doc(job, working_dir)
        if result.get("ok"):
            path = result.get("data", {}).get("path")
            if path:
                job_mod.record_digital_file(ctx.jobs_root, job_id, path)
        return result

    task_id = ctx.tasks.start(work)
    return 200, {"ok": True, "task_id": task_id}


@route("POST", "/api/jobs/<job_id>/photoshop/export-digital")
def export_photoshop_digital(ctx, body, job_id):
    job = job_mod.load_job(ctx.jobs_root, job_id)
    psd_rel = job["files"].get("psd")
    if not psd_rel:
        raise job_mod.JobError(
            "No Photoshop file yet -- click \"Create Photoshop file\" first."
        )

    root = job_mod.job_path(ctx.jobs_root, job_id)
    psd_path = root / psd_rel
    export_dirs = _digital_export_dirs(job, root)

    def work() -> dict:
        return photoshop.export_digital(job, psd_path, export_dirs)

    task_id = ctx.tasks.start(work)
    return 200, {"ok": True, "task_id": task_id}


@route("POST", "/api/adobe/open-scripts-folder")
def open_scripts_folder(ctx, body):
    """The manual fallback path when COM automation fails (SPEC.md
    §6.3): she runs the JSX herself from File > Scripts > Other
    Script..., picking job.json when prompted."""
    open_path(app_paths.bundled_root() / "adobe" / "illustrator", reveal=True)
    return 200, {"ok": True}


@route("POST", "/api/adobe/open-photoshop-scripts-folder")
def open_photoshop_scripts_folder(ctx, body):
    open_path(app_paths.bundled_root() / "adobe" / "photoshop", reveal=True)
    return 200, {"ok": True}


# -- helpers -----------------------------------------------------------


def _print_ai_paths(ctx, job: dict) -> list[Path]:
    root = job_mod.job_path(ctx.jobs_root, job["id"])
    return [root / rel for rel in (job["files"].get("print") or [])]


def _digital_export_dirs(job: dict, root: Path) -> dict[str, Path]:
    kinds = {fmt["kind"] for fmt in job["formats"] if fmt["kind"] != "print"}
    return {kind: root / "04_export" / EXPORT_SUBDIR_BY_KIND[kind] for kind in kinds}


def _summarize(job: dict, ctx) -> dict:
    status = _deliverable_status(job, ctx)
    done = sum(1 for d in status if d["status"] in ("ok", "warn", "found"))
    counts = {"ok": 0, "warn": 0, "fail": 0, "missing": 0}
    for d in status:
        counts["ok" if d["status"] == "found" else d["status"]] += 1
    return {
        "id": job["id"],
        "name": job["name"],
        "created": job["created"],
        "version": job["version"],
        "deliverables_done": done,
        "deliverables_total": len(status),
        "counts": counts,
        # just enough for the little proportional shapes in the job list
        "shapes": [_shape(f) for f in job["formats"][:8]],
    }


def _shape(fmt: dict) -> dict:
    size = fmt["panels"][0] if fmt.get("panels") else fmt["size"]
    unit = fmt.get("unit") or fmt["size"]["unit"]
    return {"w": size["w"], "h": size["h"], "unit": unit, "kind": fmt["kind"]}


def _deliverable_status(job: dict, ctx) -> list[dict]:
    if ctx.poller is not None:
        return deliverables_table(job, ctx.poller.results_for(job["id"]))
    return _naive_deliverable_status(job, ctx.jobs_root)


def _naive_deliverable_status(job: dict, jobs_root: Path) -> list[dict]:
    # Fallback for a context with no poller wired up: just "is a file
    # with this name there", with none of the real pass/warn/fail
    # checks. Kept simple and separate from deliverables_table()'s
    # "ok"/"warn"/"fail"/"missing" vocabulary so the two are never
    # confused for each other in a response.
    export_root = jobs_root / job["id"] / "04_export"
    path_by_stem: dict[str, Path] = {}
    if export_root.exists():
        for p in export_root.rglob("*"):
            if p.is_file():
                path_by_stem[p.stem] = p

    rows = []
    for d in job["deliverables"]:
        found = path_by_stem.get(d["expected_stem"])
        rows.append(
            {
                **d,
                "status": "found" if found else "missing",
                "found_file": found.name if found else None,
                "checks": [],
            }
        )
    return collapse_alternatives(rows)
