"""Video and brand-piece API (ROADMAP R5-R7): the job page's Video step
and the assistant tools call these."""

from __future__ import annotations

import shutil
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.video import concat, recipes, service
from studio_helper.video import plan as video_plan

from .dispatch import route


def _concat_path(ctx) -> str | None:
    return getattr(ctx.config, "concat_path", "") or None


@route("GET", "/api/concat/status")
def concat_status(ctx, body):
    """Starts Concat once to read its version (Setup check)."""
    return 200, {"ok": True, "concat": concat.status(_concat_path(ctx), [ctx.jobs_root])}


@route("GET", "/api/jobs/<job_id>/video")
def get_video(ctx, body, job_id):
    job = service.scan_masters(ctx.jobs_root, job_id)  # videos she dropped in herself
    v = service.section(job)
    return 200, {
        "ok": True,
        "masters": v["masters"],
        "fill": v["fill"],
        "brand_color": v.get("brand_color"),
        "motion": v.get("motion") or {"recipes": recipes.DEFAULT_RECIPES,
                                      "length_s": recipes.DEFAULT_LENGTH_S},
        "screens": service.overview(job),
        "pieces": job.get("pieces", []),
        "plan": video_plan.video_plan(job),
        "warnings": service.upscale_warnings(job),
        "recipes": list(recipes.RECIPES),
        "anchors": list(recipes.ANCHORS),
        "effects": list(recipes.EFFECTS),
    }


def _place_upload(body: dict, folder: Path) -> Path:
    tmp = Path(body["tmp"])
    name = Path(body.get("name") or "upload").name  # never a path from the browser
    folder.mkdir(parents=True, exist_ok=True)
    dest = service._unique(folder, name)
    shutil.copyfile(tmp, dest)
    return dest


@route("POST", "/api/jobs/<job_id>/upload")
def upload(ctx, body, job_id):
    """Drag-and-drop uploads (the server streams the file to `tmp`):
    to=video (a Higgsfield master), to=piece (a brand piece),
    to=motion-b&format=<id> (the second static for a crossfade)."""
    body = body or {}
    if "tmp" not in body:
        raise job_mod.JobError("Send the file itself.")
    root = job_mod.job_path(ctx.jobs_root, job_id)
    to = body.get("to")
    name = Path(body.get("name") or "").suffix.lower()
    if to == "video":
        if name not in service.MASTER_EXTS:
            raise service.VideoError("Masters must be MP4 or MOV videos.")
        dest = _place_upload(body, root / service.VIDEO_DIR)
        job, warnings = service.add_master(ctx.jobs_root, job_id, dest, copy=False)
        return 200, {"ok": True, "masters": job["video"]["masters"], "warnings": warnings}
    if to == "piece":
        if name not in recipes.PIECE_EXTS:
            raise service.VideoError("Brand pieces must be PNG, JPG or WEBP.")
        dest = _place_upload(body, root / service.PIECES_DIR)
        job = service.add_piece(ctx.jobs_root, job_id, dest, body.get("label"))
        return 200, {"ok": True, "pieces": job["pieces"]}
    if to == "motion-b":
        fid = body.get("format")
        if name not in recipes.PIECE_EXTS or not fid:
            raise service.VideoError("The second picture must be PNG or JPG, for one size.")
        dest = _place_upload(body, root / "02_assets" / "motion-b")
        rel = dest.relative_to(root).as_posix()
        job = job_mod.update_job(
            ctx.jobs_root, job_id,
            lambda j: service.section(j).setdefault("motion", {}).setdefault("b_files", {})
            .__setitem__(fid, rel))
        return 200, {"ok": True, "motion": service.section(job)["motion"]}
    raise job_mod.JobError("Unknown upload.")


@route("POST", "/api/jobs/<job_id>/video/juice")
def set_juice(ctx, body, job_id):
    body = body or {}
    service.set_juice(ctx.jobs_root, job_id, body.get("master", ""), body.get("keys") or [],
                      body.get("format_id"))
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/fill")
def set_fill(ctx, body, job_id):
    body = body or {}
    service.set_fill(ctx.jobs_root, job_id, body.get("fill", ""), body.get("format_id"),
                     body.get("brand_color"))
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/screen")
def set_screen(ctx, body, job_id):
    body = dict(body or {})
    fid = body.pop("format_id", None)
    if not fid:
        raise job_mod.JobError("Which size?")
    allowed = {k: body[k] for k in ("mode", "master") if k in body}
    if allowed.get("mode") not in (None, "fit", "motion"):
        raise service.VideoError("Mode must be fit or motion.")
    service.set_screen(ctx.jobs_root, job_id, fid, **allowed)
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/motion")
def set_motion(ctx, body, job_id):
    body = body or {}
    service.set_motion(ctx.jobs_root, job_id, body.get("recipes"), body.get("length_s"),
                       body.get("format_id"))
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/render")
def render(ctx, body, job_id):
    """Makes every video size (or `format_ids`) through Concat, one by
    one, as a task with progress."""
    body = body or {}
    job_mod.load_job(ctx.jobs_root, job_id)  # 404-ish early for a bad id
    exe = concat.find_concat(_concat_path(ctx))
    if exe is None:
        raise service.VideoError("Concat isn't installed. Install it (free, "
                                 "concatenate.pages.dev), then try again.")

    def work(report) -> dict:
        result = service.render_all(ctx.jobs_root, job_id, body.get("format_ids"), report,
                                    concat_exe=exe, overwrite=bool(body.get("overwrite")))
        return {"ok": not result["failed"], "data": result,
                "errors": [{"code": "RENDER_FAILED", "message": f["error"],
                            "format_id": f["format_id"]} for f in result["failed"]],
                "warnings": [{"code": "SKIPPED", "message": s["reason"],
                              "format_id": s["format_id"]} for s in result["skipped"]]}

    return 200, {"ok": True, "task_id": ctx.tasks.start(work, progress=True)}


@route("POST", "/api/jobs/<job_id>/video/reveal")
def reveal(ctx, body, job_id):
    """Opens one size's Concat project folder to fine-tune it in Concat."""
    from .openers import open_path
    fid = (body or {}).get("format_id", "")
    folder = job_mod.job_path(ctx.jobs_root, job_id) / service.PROJECTS_DIR / fid
    if not fid or not folder.is_dir():
        raise job_mod.JobError("Make the video first; then its Concat project is there.")
    open_path(folder)
    return 200, {"ok": True, "folder": str(folder)}


# -- brand pieces ----------------------------------------------------------------


@route("POST", "/api/jobs/<job_id>/pieces/order")
def order_pieces(ctx, body, job_id):
    job = service.reorder_pieces(ctx.jobs_root, job_id, (body or {}).get("order") or [])
    return 200, {"ok": True, "pieces": job["pieces"]}


@route("POST", "/api/jobs/<job_id>/pieces/from-library")
def piece_from_library(ctx, body, job_id):
    name = Path((body or {}).get("name") or "").name
    src = service.library_dir() / name
    if not name or not src.is_file():
        raise service.VideoError("That piece isn't in the library.")
    job = service.add_piece(ctx.jobs_root, job_id, src)
    return 200, {"ok": True, "pieces": job["pieces"]}


@route("POST", "/api/jobs/<job_id>/pieces/<piece_id>")
def update_piece(ctx, body, job_id, piece_id):
    body = dict(body or {})
    fid = body.pop("format_id", None)
    job = service.update_piece(ctx.jobs_root, job_id, piece_id, body, fid)
    return 200, {"ok": True, "pieces": job["pieces"]}


@route("POST", "/api/jobs/<job_id>/pieces/<piece_id>/remove")
def remove_piece(ctx, body, job_id, piece_id):
    job = service.remove_piece(ctx.jobs_root, job_id, piece_id)
    return 200, {"ok": True, "pieces": job["pieces"]}


@route("POST", "/api/jobs/<job_id>/pieces/<piece_id>/library")
def save_piece_to_library(ctx, body, job_id, piece_id):
    return 200, {"ok": True, "saved": service.save_to_library(ctx.jobs_root, job_id, piece_id)}


@route("GET", "/api/pieces/library")
def get_library(ctx, body):
    return 200, {"ok": True, "library": service.library()}
