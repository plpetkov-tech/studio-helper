"""Video and brand-piece API (ROADMAP R5-R7): the job page's Video step
and the assistant tools call these."""

from __future__ import annotations

import shutil
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.video import concat, motion, recipes, service
from studio_helper.video import plan as video_plan

from .dispatch import route


def _concat_path(ctx) -> str | None:
    return getattr(ctx.config, "concat_path", "") or None


@route("GET", "/api/concat/status")
def concat_status(ctx, body):
    """Starts Concat once to read its version (Setup check)."""
    return 200, {"ok": True, "concat": concat.status(_concat_path(ctx), [ctx.jobs_root])}


def _options() -> dict:
    """The choices the Video tab and assistants offer, with Figma's names."""
    return {
        "anchors": list(recipes.ANCHORS),
        "enter_effects": list(motion.ENTER_EFFECTS),
        "exit_effects": list(motion.EXIT_EFFECTS),
        "directions": list(motion.DIRECTIONS),
        "transitions": list(motion.TRANSITIONS),
        "camera_moves": list(motion.CAMERA_MOVES),
        "openings": list(recipes.OPENINGS),
        "endings": list(recipes.ENDINGS),
        "springs": {k: dict(v, duration_s=motion.spring_duration(v))
                    for k, v in motion.SPRINGS.items()},
        "curves": motion.CURVES,
    }


@route("GET", "/api/jobs/<job_id>/video")
def get_video(ctx, body, job_id):
    job = service.scan_masters(ctx.jobs_root, job_id)  # videos she dropped in herself
    root = job_mod.job_path(ctx.jobs_root, job_id)
    v = service.section(job)
    m = v.get("motion") or {}
    screens = service.overview(job)
    by_id = {f["id"]: f for f in job["formats"]}
    for row in screens:
        fmt = by_id[row["format_id"]]
        pic = recipes.static_for(job, fmt, root)
        second = recipes.second_for(job, fmt, root)
        own = v["screens"].get(fmt["id"], {})
        row.update(
            picture=pic.relative_to(root).as_posix() if pic else None,
            picture_own=fmt["id"] in m.get("a_files", {}),
            second=second.relative_to(root).as_posix() if second else None,
            own_motion=bool(own.get("motion") or own.get("recipes")),
            own_mode=own.get("mode"),
            piece_hidden={pid: True for pid, o in (own.get("pieces") or {}).items()
                          if o.get("hidden")},
            motion=recipes.motion_settings(job, fmt),
            video_added=bool(fmt.get("video_added")),
        )
    return 200, {
        "ok": True,
        "source": v.get("source") or ("fit" if v["masters"] else None),
        "masters": v["masters"],
        "fill": v["fill"],
        "brand_color": v.get("brand_color"),
        "motion": recipes.motion_settings(job),
        "screens": screens,
        "candidates": service.video_candidates(job),
        "pieces": job.get("pieces", []),
        "plan": video_plan.video_plan(job),
        "warnings": service.upscale_warnings(job),
        "options": _options(),
    }


@route("GET", "/api/jobs/<job_id>/video/preview/<format_id>")
def get_preview(ctx, body, job_id, format_id):
    """One size's video as layers and keyframes, for the live preview."""
    return 200, {"ok": True, "preview": service.preview(ctx.jobs_root, job_id, format_id)}


@route("POST", "/api/jobs/<job_id>/video/source")
def set_source(ctx, body, job_id):
    service.set_source(ctx.jobs_root, job_id, (body or {}).get("source", ""))
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/picture")
def clear_picture(ctx, body, job_id):
    """Back to her exported static (which=a), or no 2nd picture (which=b)."""
    body = body or {}
    if body.get("which") not in ("a", "b") or not body.get("format_id"):
        raise service.VideoError("Which size, and which picture?")
    service.set_picture(ctx.jobs_root, job_id, body["format_id"], body["which"], None)
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/enable")
def enable_video(ctx, body, job_id):
    """Also make a video for sizes that only had a picture."""
    service.enable_video(ctx.jobs_root, job_id, (body or {}).get("format_ids") or [])
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/disable")
def disable_video(ctx, body, job_id):
    service.disable_video(ctx.jobs_root, job_id, (body or {}).get("format_id", ""))
    return get_video(ctx, None, job_id)


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
    if to in ("motion-a", "motion-b"):
        # her own picture for one size's motion (a: instead of the export,
        # e.g. without the logo she animates; b: the 2nd picture)
        fid = body.get("format")
        if name not in recipes.PICTURE_EXTS or not fid:
            raise service.VideoError("The picture must be PNG or JPG, for one size.")
        dest = _place_upload(body, root / "02_assets" / to)
        rel = dest.relative_to(root).as_posix()
        job = service.set_picture(ctx.jobs_root, job_id, fid, to[-1], rel)
        warnings = _picture_warnings(job, fid, dest)
        return 200, {"ok": True, "motion": service.section(job)["motion"], "warnings": warnings}
    raise job_mod.JobError("Unknown upload.")


def _picture_warnings(job: dict, format_id: str, path: Path) -> list[str]:
    fmt = next((f for f in job["formats"] if f["id"] == format_id), None)
    if not fmt:
        return []
    w, h = recipes._image_size(path)
    dw, dh = fmt["size"]["w"], fmt["size"]["h"]
    if (w, h) == (dw, dh):
        return []
    if abs(w / h - dw / dh) > 0.01:
        return [f"That picture is {w} × {h}, a different shape from {dw} × {dh}: it will show "
                "with bars. Export it at the size's own shape."]
    return [f"That picture is {w} × {h}; the video is {dw} × {dh}. It's scaled to fit."]


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
    allowed = {k: body[k] for k in ("mode", "master", "repeat") if k in body}
    if allowed.get("mode") not in (None, "fit", "motion"):
        raise service.VideoError("Mode must be fit or motion.")
    if allowed.get("repeat") not in (None, 0, 1, 2, 3, 4):
        raise service.VideoError("Repeat 1 to 4 times.")
    service.set_screen(ctx.jobs_root, job_id, fid, **allowed)
    return get_video(ctx, None, job_id)


@route("POST", "/api/jobs/<job_id>/video/motion")
def set_motion(ctx, body, job_id):
    """Motion settings: {changes: {feel, camera, opening, second, ending,
    length_s, use_pieces}, format_id?, reset?}; older clients send
    recipes / length_s."""
    body = body or {}
    service.set_motion(ctx.jobs_root, job_id, body.get("changes"), body.get("format_id"),
                       body.get("recipes"), body.get("length_s"), bool(body.get("reset")))
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
