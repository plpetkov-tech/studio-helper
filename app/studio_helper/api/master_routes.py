"""One master, cut to every size (master.py): the Files & export tab's
master section."""

from __future__ import annotations

from studio_helper import master as M
from studio_helper.adobe import illustrator, photoshop
from studio_helper.adobe.bridge import AdobeBridgeError
from studio_helper.api.dispatch import route
from studio_helper.core import job as job_mod

PNG_EXPORT_MAX_PX = 8000  # Illustrator's PNG export stays below its size limit


def _view(ctx, job_id: str, job: dict | None = None) -> tuple[int, dict]:
    job = job or job_mod.load_job(ctx.jobs_root, job_id)
    root = job_mod.job_path(ctx.jobs_root, job_id)
    return 200, {"ok": True, "master": M.view(job, root)}


@route("GET", "/api/jobs/<job_id>/master")
def get_master(ctx, body, job_id):
    return _view(ctx, job_id)


@route("POST", "/api/jobs/<job_id>/master")
def set_master(ctx, body, job_id):
    """{mode?, app?, box?, format_id?, reset?, fill?, brand_color?}"""
    body = body or {}
    job = M.update(ctx.jobs_root, job_id, mode=body.get("mode"), app=body.get("app"),
                   box=body.get("box"), format_id=body.get("format_id"),
                   reset=bool(body.get("reset")), fill=body.get("fill"),
                   brand_color=body.get("brand_color"))
    return _view(ctx, job_id, job)


@route("POST", "/api/jobs/<job_id>/master/make")
def make_master(ctx, body, job_id):
    """Makes the master in Illustrator or Photoshop (or opens it, if it's
    already there)."""
    job = job_mod.load_job(ctx.jobs_root, job_id)
    root = job_mod.job_path(ctx.jobs_root, job_id)
    m = M.section(job)
    plan = M.master_size(job, m["app"])
    rel = m.get("file") or M.master_file(job, m["app"])
    path = root / rel
    cmyk = m["app"] == "ai" and any(f["kind"] == "print" for f in M.cut_sizes(job, "ai"))

    def work() -> dict:
        if m["app"] == "ai":
            result = illustrator.make_master(path, plan["w"], plan["h"], cmyk)
        else:
            result = photoshop.make_master(path, plan["w"], plan["h"])
        if result.get("ok") and not m.get("file"):
            M.record_made(ctx.jobs_root, job_id, rel, plan["w"], plan["h"])
        return result

    return 200, {"ok": True, "task_id": ctx.tasks.start(work)}


@route("POST", "/api/jobs/<job_id>/master/read")
def read_master(ctx, body, job_id):
    """Exports the master's picture (saving her open master first) and
    keeps it as 02_assets/master/master.png for the box and the cut."""
    job = job_mod.load_job(ctx.jobs_root, job_id)
    root = job_mod.job_path(ctx.jobs_root, job_id)
    m = M.section(job)
    if not m.get("file"):
        raise M.MasterError("Make the master first.")
    path = root / m["file"]
    out = root / "03_working" / "master" / "_read.png"

    def work() -> dict:
        out.parent.mkdir(parents=True, exist_ok=True)
        if m["app"] == "ai":
            longest = max(m.get("w") or 1, m.get("h") or 1)
            scale = min(100.0, 100.0 * PNG_EXPORT_MAX_PX / longest)
            result = illustrator.export_master(path, out, scale)
        else:
            result = photoshop.export_master(path, out)
        if result.get("ok"):
            M.record_preview(ctx.jobs_root, job_id, M.take_preview(root, out))
            out.unlink(missing_ok=True)
        return result

    return 200, {"ok": True, "task_id": ctx.tasks.start(work)}


@route("POST", "/api/jobs/<job_id>/master/cut")
def cut_master(ctx, body, job_id):
    """Cuts the master into every size: digital sizes into 04_export,
    print sizes (Illustrator master) into her Illustrator print file,
    which is created first if there isn't one. {overwrite: true}
    replaces digital files she exported herself."""
    body = body or {}
    job = job_mod.load_job(ctx.jobs_root, job_id)
    m = M.section(job)
    sizes = M.cut_sizes(job, m["app"])
    digital = [f for f in sizes if f["kind"] != "print"]
    prints = [f for f in sizes if f["kind"] == "print"]
    if not sizes:
        raise M.MasterError("This job has no sizes a master can be cut into.")
    if digital and not m.get("preview"):
        raise M.MasterError("Read the master first, so the app has its picture.")
    if prints and not m.get("file"):
        raise M.MasterError("Make the master first.")

    def work(report) -> dict:
        out = {"made": [], "kept": [], "failed": [], "print": [], "warnings": []}
        if digital:
            res = M.cut_digital(ctx.jobs_root, job_id, bool(body.get("overwrite")),
                                lambda i, n, name: report({"done": i, "total": n + bool(prints),
                                                           "label": name, "fraction": 0.0}))
            out.update(made=res["made"], kept=res["kept"], failed=res["failed"])
        if prints:
            report({"done": len(digital), "total": len(digital) + 1,
                    "label": "Print, in Illustrator", "fraction": 0.0})
            try:
                out["print"], warnings = _cut_print(ctx, job_id)
                out["warnings"] += warnings
            except (AdobeBridgeError, M.MasterError) as exc:
                why = (f"Illustrator didn't respond: {exc}" if isinstance(exc, AdobeBridgeError)
                       else str(exc))
                out["failed"] += [{"format_id": f["id"], "error": why} for f in prints]
        ok = not out["failed"]
        return {"ok": ok, "data": out,
                "errors": [{"code": "CUT_FAILED", "message": f["error"],
                            "format_id": f["format_id"]} for f in out["failed"]],
                "warnings": [{"code": "CUT", "message": w} for w in out["warnings"]]}

    return 200, {"ok": True, "task_id": ctx.tasks.start(work, progress=True)}


def _cut_print(ctx, job_id: str) -> tuple[list[dict], list[str]]:
    job = job_mod.auto_scale_job(ctx.jobs_root, job_id)
    root = job_mod.job_path(ctx.jobs_root, job_id)
    warnings = []
    if not job_mod.current_print_files(job):  # her print file, made first
        result = illustrator.create_print_doc(job, root / "03_working")
        if not result.get("ok"):
            raise M.MasterError(" ".join(e["message"] for e in result.get("errors", []))
                                or "Couldn't create the Illustrator print file.")
        paths = [d["path"] for d in result.get("data", {}).get("documents", [])]
        job = job_mod.record_print_files(ctx.jobs_root, job_id, paths)
    m = M.section(job)
    ai_paths = [root / rel for rel in job_mod.current_print_files(job)]
    result = illustrator.cut_master(root / m["file"], ai_paths, M.print_cuts(job), m["fill"],
                                    m.get("brand_color"))
    warnings += [w["message"] for w in result.get("warnings", [])]
    if not result.get("ok"):
        raise M.MasterError(" ".join(e["message"] for e in result.get("errors", []))
                            or "Couldn't place the master in the print file.")
    cut = result.get("data", {}).get("cut", [])
    M.record_print_cuts(ctx.jobs_root, job_id, cut)
    return cut, warnings
