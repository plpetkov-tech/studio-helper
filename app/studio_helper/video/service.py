"""The job's video section (ROADMAP R6/R7): masters, juice box, fill,
brand pieces, and rendering every video size through Concat.

job["video"] = {
  "masters": [{"id", "file", "w", "h", "duration_s", "fps", "juice": [{"t", "box"}]}],
  "fill": "blur" | "black" | "color", "brand_color": "#rrggbb",
  "screens": {format_id: {"master", "fill", "juice", "mode": "fit" | "motion"}},
  "motion": {"recipes": [...], "length_s": 8},
  "renders": {format_id: {"at", "file", "project", "master", "fill", "mode"}},
}
job["pieces"] = [{"id", "file", "label", "anchor", "width_pct", "margin_pct", "enter", "exit"}]

Python stays the only writer of job.json (job.update_job).
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND
from studio_helper.validators.mp4info import Mp4Error, read_mp4

from . import plan as video_plan
from . import recipes
from . import render as R
from .concat import ConcatError, ConcatSession

VIDEO_DIR = "02_assets/video"
PIECES_DIR = "02_assets/pieces"
PROJECTS_DIR = "03_working/video"
FILLS = ("blur", "black", "color")
MASTER_EXTS = {".mp4", ".mov", ".m4v"}

# Concat renders one export at a time; so do we.
_render_lock = threading.Lock()


class VideoError(job_mod.JobError):
    pass


def section(job: dict) -> dict:
    v = job.setdefault("video", {})
    v.setdefault("masters", [])
    v.setdefault("fill", "blur")
    v.setdefault("screens", {})
    v.setdefault("renders", {})
    return v


def _unique(folder: Path, name: str) -> Path:
    dest = folder / name
    n = 2
    while dest.exists():
        dest = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return dest


def add_master(jobs_root: Path, job_id: str, src: Path,
               copy: bool = True) -> tuple[dict, list[str]]:
    """Adds a Higgsfield master: copied into 02_assets/video (her original
    is never moved), probed for size, length and frame rate."""
    root = job_mod.job_path(jobs_root, job_id)
    folder = root / VIDEO_DIR
    folder.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() not in MASTER_EXTS:
        raise VideoError("Masters must be MP4 or MOV videos.")
    dest = src if (not copy or src.parent == folder) else _unique(folder, src.name)
    if dest != src:
        shutil.copy2(src, dest)
    try:
        info = read_mp4(dest)
    except Mp4Error as exc:
        raise VideoError(f"Can't read this video: {exc}.") from exc
    if not info.has_video:
        raise VideoError("This file has no video in it.")
    rel = dest.relative_to(root).as_posix()

    def change(job):
        v = section(job)
        if any(m["file"] == rel for m in v["masters"]):
            return
        n = 1 + max((int(m["id"][1:]) for m in v["masters"] if m["id"][1:].isdigit()), default=0)
        v["masters"].append({"id": f"m{n}", "file": rel, "w": info.width, "h": info.height,
                             "duration_s": round(info.duration_s, 3), "fps": info.fps,
                             "juice": []})

    job = job_mod.update_job(jobs_root, job_id, change)
    return job, upscale_warnings(job)


def upscale_warnings(job: dict) -> list[str]:
    """Screens whose master would be enlarged more than 1.5x, using the
    real fit (juice box, fill on strips), so only real problems show."""
    out = []
    plan_by_screen = {s["id"]: m for m in video_plan.video_plan(job)["masters"]
                      for s in m["screens"]}
    for row in overview(job):
        if row.get("scale", 0) > video_plan.UPSCALE_WARN:
            m = plan_by_screen.get(row["format_id"])
            want = (f"a {m['ratio']} master at least {m['min_w']} × {m['min_h']}"
                    if m else "a bigger master")
            out.append(f"{row['name']} would enlarge the video {row['scale']:.1f}×: "
                       f"make {want} in Higgsfield (or upscale it there).")
    return out


def scan_masters(jobs_root: Path, job_id: str) -> dict:
    """Picks up videos she dropped into 02_assets/video herself."""
    root = job_mod.job_path(jobs_root, job_id)
    folder = root / VIDEO_DIR
    job = job_mod.load_job(jobs_root, job_id)
    known = {m["file"] for m in section(job)["masters"]}
    if folder.is_dir():
        for f in sorted(folder.iterdir()):
            rel = f.relative_to(root).as_posix()
            if f.is_file() and f.suffix.lower() in MASTER_EXTS and rel not in known:
                try:
                    job, _ = add_master(jobs_root, job_id, f, copy=False)
                except VideoError:
                    continue
    return job


def set_juice(jobs_root: Path, job_id: str, master_id: str, keys: list[dict],
              format_id: str | None = None) -> dict:
    """keys: [{"t": seconds, "box": [x, y, w, h] fractions}]; per screen
    when format_id is given (her own box for one screen)."""
    for k in keys:
        box = k.get("box") or []
        if len(box) != 4 or not all(0 <= float(b) <= 1 for b in box) or box[2] <= 0 or box[3] <= 0:
            raise VideoError("The juice box must be inside the video frame.")
    clean = [{"t": float(k.get("t", 0)), "box": [float(b) for b in k["box"]]} for k in keys]

    def change(job):
        v = section(job)
        if format_id:
            v["screens"].setdefault(format_id, {})["juice"] = clean
            v["screens"][format_id]["master"] = master_id
            return
        m = next((m for m in v["masters"] if m["id"] == master_id), None)
        if m is None:
            raise VideoError("That master isn't in this job.")
        m["juice"] = clean

    return job_mod.update_job(jobs_root, job_id, change)


def set_fill(jobs_root: Path, job_id: str, fill: str, format_id: str | None = None,
             brand_color: str | None = None) -> dict:
    if fill not in FILLS and not (format_id and fill == "job"):
        raise VideoError("Fill must be blur, black or colour.")

    def change(job):
        v = section(job)
        if brand_color:
            v["brand_color"] = brand_color
        if format_id:
            s = v["screens"].setdefault(format_id, {})
            if fill == "job":
                s.pop("fill", None)
            else:
                s["fill"] = fill
        else:
            v["fill"] = fill

    return job_mod.update_job(jobs_root, job_id, change)


def set_screen(jobs_root: Path, job_id: str, format_id: str, **settings) -> dict:
    """Per-screen choices: master, mode ("fit" a master / "motion" from statics)."""
    def change(job):
        s = section(job)["screens"].setdefault(format_id, {})
        for k, val in settings.items():
            if val is None:
                s.pop(k, None)
            else:
                s[k] = val

    return job_mod.update_job(jobs_root, job_id, change)


# -- what each screen will get -----------------------------------------------


def _best_master(fmt: dict, masters: list[dict]) -> dict | None:
    if not masters:
        return None
    r = fmt["size"]["w"] / fmt["size"]["h"]
    return max(masters, key=lambda m: (video_plan.coverage(m["w"] / m["h"], r), m["w"] * m["h"]))


def screen_settings(job: dict, fmt: dict) -> dict:
    v = section(job)
    s = v["screens"].get(fmt["id"], {})
    masters = v["masters"]
    master = (next((m for m in masters if m["id"] == s.get("master")), None)
              or _best_master(fmt, masters))
    juice = s.get("juice") or (master or {}).get("juice") or []
    return {
        "mode": s.get("mode") or ("fit" if master else "motion"),
        "master": master,
        "fill": s.get("fill") or v["fill"],
        "juice": juice,
        "brand_color": v.get("brand_color"),
    }


def overview(job: dict) -> list[dict]:
    """One row per video size: what it will be rendered from, how much
    fill shows, and what was rendered last."""
    from . import fit as F
    rows = []
    v = section(job)
    for fmt in video_plan.video_formats(job):
        st = screen_settings(job, fmt)
        row = {"format_id": fmt["id"], "name": fmt.get("name", fmt["id"]),
               "w": fmt["size"]["w"], "h": fmt["size"]["h"], "mode": st["mode"],
               "fill": st["fill"], "master": (st["master"] or {}).get("id"),
               "max_duration_s": fmt.get("max_duration_s"),
               "rendered": v["renders"].get(fmt["id"])}
        m = st["master"]
        if st["mode"] == "fit" and m:
            band = fmt.get("ui_safe_px") or {}
            keys = [(k["t"], F.juice_box(k["box"], m["w"], m["h"])) for k in st["juice"]]
            fits = F.fit_keyed(m["w"], m["h"], fmt["size"]["w"], fmt["size"]["h"], keys,
                               band.get("top", 0), band.get("bottom", 0))
            f = fits[0][1]
            row.update(fill_fraction=f.fill_fraction, scale=f.scale,
                       left=f.left, top=f.top, strip=f.fill_fraction > 0.5)
        rows.append(row)
    return rows


# -- rendering -----------------------------------------------------------------


def _output_for(job: dict, fmt: dict, root: Path) -> Path | None:
    d = next((d for d in job["deliverables"]
              if d["format_id"] == fmt["id"] and d["type"] == "mp4"), None)
    if d is None:
        return None
    return root / "04_export" / EXPORT_SUBDIR_BY_KIND[fmt["kind"]] / f"{d['expected_stem']}.mp4"


def render_all(jobs_root: Path, job_id: str, format_ids: list[str] | None = None,
               report=lambda info: None, concat_exe: Path | None = None,
               concat_env: dict | None = None, overwrite: bool = False,
               concat_command: list[str] | None = None) -> dict:
    """Renders every video size (or `format_ids`) one after another and
    exports each to its deliverable file; the poller then checks them.
    A file at that name not made by us is never overwritten unless asked."""
    if not _render_lock.acquire(blocking=False):
        raise VideoError("Videos are already being made for a job. Wait for it to finish.")
    try:
        return _render_all(jobs_root, job_id, format_ids, report, concat_exe, concat_env,
                           overwrite, concat_command)
    finally:
        _render_lock.release()


def _render_all(jobs_root, job_id, format_ids, report, concat_exe, concat_env, overwrite,
                concat_command=None):
    root = job_mod.job_path(jobs_root, job_id)
    job = job_mod.load_job(jobs_root, job_id)
    v = section(job)
    targets = [f for f in video_plan.video_formats(job)
               if format_ids is None or f["id"] in format_ids]
    done, skipped, failed = [], [], []
    with ConcatSession([jobs_root], exe=concat_exe, env=concat_env,
                       command=concat_command) as c:
        for i, fmt in enumerate(targets):
            name = fmt.get("name", fmt["id"])
            report({"done": i, "total": len(targets), "label": name, "fraction": 0.0})
            out = _output_for(job, fmt, root)
            if out is None:
                skipped.append({"format_id": fmt["id"], "reason": "No MP4 is expected for it."})
                continue
            rel_out = out.relative_to(root).as_posix()
            ours = (v["renders"].get(fmt["id"]) or {}).get("file") == rel_out
            if out.exists() and not ours and not overwrite:
                skipped.append({"format_id": fmt["id"],
                                "reason": f"{out.name} is already there and wasn't made here. "
                                          "Replace it?"})
                continue
            try:
                plan, meta = _plan_for(job, fmt, root)
                project = root / PROJECTS_DIR / fmt["id"]
                path = R.build(c, plan, project)
                R.export(c, path, plan, out,
                         lambda f, i=i, name=name: report({"done": i, "total": len(targets),
                                                           "label": name, "fraction": f}))
                c.call("project_close", path=path, save=True)
                record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                          "file": out.relative_to(root).as_posix(),
                          "project": project.relative_to(root).as_posix(), **meta}
                job = job_mod.update_job(jobs_root, job_id,
                                         lambda j, f=fmt["id"], r=record:
                                         section(j)["renders"].__setitem__(f, r))
                v = section(job)
                done.append(fmt["id"])
            except (ConcatError, VideoError) as exc:
                failed.append({"format_id": fmt["id"], "error": str(exc)})
    report({"done": len(targets), "total": len(targets), "label": "", "fraction": 1.0})
    return {"rendered": done, "skipped": skipped, "failed": failed}


def _plan_for(job: dict, fmt: dict, root: Path) -> tuple[R.RenderPlan, dict]:
    st = screen_settings(job, fmt)
    if st["mode"] == "fit":
        m = st["master"]
        if not m:
            raise VideoError("Add a Higgsfield video first, or use motion from statics.")
        plan, _fits = R.fitter_plan(fmt, m, str(root / m["file"]), st["fill"], st["brand_color"],
                                    st["juice"])
        # brand pieces arrive as an end card over the video
        recipes.add_pieces(plan, recipes.piece_layers(job, fmt, root, end_s=plan.duration))
        return plan, {"mode": "fit", "master": m["id"], "fill": st["fill"]}
    plan = recipes.motion_plan(job, fmt, root)
    return plan, {"mode": "motion", "recipes": recipes.job_recipes(job, fmt)}


# -- brand pieces (R7) -----------------------------------------------------------


def _piece_defaults(n: int) -> dict:
    return {"anchor": "bottom-center", "width_pct": 30 if n == 0 else 22, "margin_pct": 5,
            "enter": {"effect": "fade-up"}, "exit": None}


def add_piece(jobs_root: Path, job_id: str, src: Path, label: str | None = None) -> dict:
    """Copies a brand piece (logo, line, promo text...) into 02_assets/pieces."""
    if src.suffix.lower() not in recipes.PIECE_EXTS:
        raise VideoError("Brand pieces must be PNG, JPG or WEBP (transparent PNG is best).")
    root = job_mod.job_path(jobs_root, job_id)
    folder = root / PIECES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    dest = src if src.parent == folder else _unique(folder, src.name)
    if dest != src:
        shutil.copy2(src, dest)
    rel = dest.relative_to(root).as_posix()

    def change(job):
        pieces = job.setdefault("pieces", [])
        if any(p["file"] == rel for p in pieces):
            return
        n = 1 + max((int(p["id"][1:]) for p in pieces if p["id"][1:].isdigit()), default=0)
        pieces.append({"id": f"p{n}", "file": rel, "label": label or Path(rel).stem,
                       **_piece_defaults(len(pieces))})

    return job_mod.update_job(jobs_root, job_id, change)


PIECE_FIELDS = {"label", "anchor", "width_pct", "margin_pct", "enter", "exit"}


def update_piece(jobs_root: Path, job_id: str, piece_id: str, changes: dict,
                 format_id: str | None = None) -> dict:
    bad = set(changes) - PIECE_FIELDS
    if bad:
        raise VideoError(f"Can't change {', '.join(sorted(bad))} on a brand piece.")
    if "anchor" in changes and changes["anchor"] not in recipes.ANCHORS:
        raise VideoError("Unknown position for the piece.")
    if "width_pct" in changes and not 2 <= float(changes["width_pct"]) <= 100:
        raise VideoError("Piece size must be between 2% and 100% of the width.")
    effect = (changes.get("enter") or {}).get("effect")
    if effect and effect not in recipes.EFFECTS:
        raise VideoError("Unknown entrance effect.")

    def change(job):
        if format_id:
            over = section(job)["screens"].setdefault(format_id, {}).setdefault("pieces", {})
            over.setdefault(piece_id, {}).update(changes)
            return
        p = next((p for p in job.get("pieces", []) if p["id"] == piece_id), None)
        if p is None:
            raise VideoError("That brand piece isn't in this job.")
        p.update(changes)

    return job_mod.update_job(jobs_root, job_id, change)


def reorder_pieces(jobs_root: Path, job_id: str, order: list[str]) -> dict:
    def change(job):
        pieces = {p["id"]: p for p in job.get("pieces", [])}
        if set(order) != set(pieces):
            raise VideoError("The new order must list every piece once.")
        job["pieces"] = [pieces[i] for i in order]

    return job_mod.update_job(jobs_root, job_id, change)


def remove_piece(jobs_root: Path, job_id: str, piece_id: str) -> dict:
    """Takes the piece off the job; its file stays in 02_assets/pieces."""
    def change(job):
        job["pieces"] = [p for p in job.get("pieces", []) if p["id"] != piece_id]

    return job_mod.update_job(jobs_root, job_id, change)


def library_dir() -> Path:
    from studio_helper import paths
    return paths.app_data_dir() / "pieces"


def library() -> list[dict]:
    folder = library_dir()
    if not folder.is_dir():
        return []
    return [{"name": f.name, "path": str(f)} for f in sorted(folder.iterdir())
            if f.is_file() and f.suffix.lower() in recipes.PIECE_EXTS]


def save_to_library(jobs_root: Path, job_id: str, piece_id: str) -> dict:
    """Keeps a piece (the logo is the same on every job) for reuse."""
    job = job_mod.load_job(jobs_root, job_id)
    p = next((p for p in job.get("pieces", []) if p["id"] == piece_id), None)
    if p is None:
        raise VideoError("That brand piece isn't in this job.")
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    src = job_mod.job_path(jobs_root, job_id) / p["file"]
    dest = folder / src.name
    if not dest.exists():
        shutil.copy2(src, dest)
    return {"name": dest.name, "path": str(dest)}


def set_motion(jobs_root: Path, job_id: str, recipes_: list[str] | None = None,
               length_s: float | None = None, format_id: str | None = None) -> dict:
    if recipes_ is not None and any(r not in recipes.RECIPES for r in recipes_):
        raise VideoError("Unknown motion recipe.")
    if length_s is not None and not 1 <= float(length_s) <= 60:
        raise VideoError("Length must be between 1 and 60 seconds.")

    def change(job):
        v = section(job)
        if format_id:
            s = v["screens"].setdefault(format_id, {})
            if recipes_ is not None:
                s["recipes"] = recipes_
            return
        m = v.setdefault("motion", {})
        if recipes_ is not None:
            m["recipes"] = recipes_
        if length_s is not None:
            m["length_s"] = float(length_s)

    return job_mod.update_job(jobs_root, job_id, change)
