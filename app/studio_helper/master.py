"""One master, cut to every size: she designs once on one big
artboard (Illustrator or Photoshop), marks what must stay with a box,
and the app cuts the master into every size of the job.

job["master"] = {
  "mode": "each" | "master",       # how she designs this job (her choice)
  "app": "ai" | "ps",              # where the master lives
  "file": "03_working/<id>_master_v01.ai",
  "w", "h",                        # the master's size (pt for .ai, px for .psd; 1:1 on screen)
  "preview": "02_assets/master/master.png", "pw", "ph", "read_at",
  "box": [x, y, w, h],             # fractions of the master; what every size keeps
  "own": {format_id: [x, y, w, h]},# a size's own box
  "fill": "blur" | "color" | "white", "brand_color": "#rrggbb",
  "cuts": {format_id: {"at", "file", "mtime", "size"}},
}

Each size shows as much of the master as fits and never cuts the box:
the smallest scale that fills the size, unless the box would then not
fit; then the box fits exactly and the rest of the size gets the fill.

Digital sizes are cut here from the master's picture (Pillow).
Print sizes (Illustrator master only) are placed, linked and clipped,
into her Illustrator print file by cut_master.jsx: vector stays vector.
A Photoshop master covers the digital sizes only; print stays in
Illustrator as usual.
"""

from __future__ import annotations

import io
import math
import time
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND

MODES = ("each", "master")
APPS = ("ai", "ps")
FILLS = ("blur", "color", "white")
DEFAULT_BOX = [0.3, 0.3, 0.4, 0.4]
PREVIEW_DIR = "02_assets/master"
PREVIEW_FILE = "master.png"
PREVIEW_SMALL = "master_small.jpg"
SMALL_SIDE = 1600
MIN_SIDE = 2000          # never a master smaller than this on its long side
PSD_MAX_PX = 30000       # Photoshop's .psd limit
AI_MAX_PT = 16383        # Illustrator's largest artboard
DIGITAL_TYPES = ("png", "jpg")


class MasterError(job_mod.JobError):
    pass


def section(job: dict) -> dict:
    m = job.setdefault("master", {})
    m.setdefault("mode", None)
    m.setdefault("app", "ai")
    m.setdefault("box", list(DEFAULT_BOX))
    m.setdefault("own", {})
    m.setdefault("fill", "blur")
    m.setdefault("cuts", {})
    return m


# -- which sizes ---------------------------------------------------------------


def _digital_type(fmt: dict) -> str | None:
    return next((t for t in fmt.get("exports", []) if t in DIGITAL_TYPES), None)


def cut_sizes(job: dict, app: str) -> list[dict]:
    """The sizes this master is cut into: digital sizes with a PNG or
    JPG, plus print sizes when the master is in Illustrator. Panelled
    formats (elevator doors, wraps) are left to her."""
    out = []
    for fmt in job["formats"]:
        if fmt.get("panels") or "size" not in fmt:
            continue
        if fmt["kind"] == "print":
            if app == "ai":
                out.append(fmt)
        elif _digital_type(fmt):
            out.append(fmt)
    return out


def left_out(job: dict, app: str) -> list[dict]:
    ids = {f["id"] for f in cut_sizes(job, app)}
    return [f for f in job["formats"] if f["id"] not in ids]


def frame_of(fmt: dict) -> tuple[float, float]:
    """The size's frame in its own units: pixels, or mm with the bleed
    on every side (the cut covers the bleed too)."""
    w, h = fmt["size"]["w"], fmt["size"]["h"]
    if fmt["kind"] == "print":
        b = fmt.get("bleed_mm") or 0
        return w + 2 * b, h + 2 * b
    return w, h


# -- the master's size ---------------------------------------------------------


def _coverage(a: float, b: float) -> float:
    return min(a / b, b / a)


def master_size(job: dict, app: str) -> dict:
    """{"w", "h", "unit", "note", "warn"}: a shape that keeps the most of
    every size, big enough that each digital size gets its full pixels
    from a fill-the-frame cut. Illustrator is vector, so print adds no
    pixels; the artboard just needs the shape."""
    sizes = cut_sizes(job, app)
    if not sizes:
        raise MasterError("This job has no sizes a master can be cut into.")
    ratios = [frame_of(f)[0] / frame_of(f)[1] for f in sizes]
    candidates = sorted({min(max(r, 9 / 16), 16 / 9) for r in ratios} | {1.0, 4 / 3, 3 / 4})
    ratio = max(candidates, key=lambda c: (sum(_coverage(c, r) for r in ratios), -abs(c - 1)))
    need_w = 0.0
    for f in sizes:
        if f["kind"] == "print":
            continue
        dw, dh = f["size"]["w"], f["size"]["h"]
        need_w = max(need_w, dw, dh * ratio)
    long_min = MIN_SIDE
    w = max(need_w, long_min if ratio >= 1 else long_min * ratio)
    w = 2 * math.ceil(w / 2)
    h = 2 * math.ceil(w / ratio / 2)
    limit = AI_MAX_PT if app == "ai" else PSD_MAX_PX
    warn = None
    if max(w, h) > limit:
        k = limit / max(w, h)
        w, h = int(w * k) // 2 * 2, int(h * k) // 2 * 2
        warn = (f"The tallest or widest size needs a bigger master than "
                f"{'Illustrator' if app == 'ai' else 'Photoshop'} allows; it was made "
                f"{w} × {h}, so that size comes out a little soft.")
    unit = "pt" if app == "ai" else "px"
    n_print = sum(1 for f in sizes if f["kind"] == "print")
    note = (f"Shaped so all {len(sizes)} sizes can be cut from it"
            + (", print included." if n_print else "."))
    return {"w": int(w), "h": int(h), "unit": unit, "note": note, "warn": warn}


# -- the fit -------------------------------------------------------------------


def clean_box(box) -> list[float]:
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError) as exc:
        raise MasterError("The box is four numbers: x, y, width, height.") from exc
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise MasterError("The box is four numbers: x, y, width, height.")
    w, h = min(max(w, 0.02), 1.0), min(max(h, 0.02), 1.0)
    x, y = min(max(x, 0.0), 1 - w), min(max(y, 0.0), 1 - h)
    return [round(v, 5) for v in (x, y, w, h)]


def fit(mw: float, mh: float, dw: float, dh: float, box) -> dict:
    """Where the master goes in a dw×dh frame: scale `s` (frame units per
    master unit) and the master's top-left `left`/`top` in the frame.
    `bands` = the box doesn't fit at a filling scale, so the fill shows.
    Mirrored in web/static/master.js (tests/web/check_master_js.js)."""
    bx, by, bw, bh = box[0] * mw, box[1] * mh, box[2] * mw, box[3] * mh
    s_cover = max(dw / mw, dh / mh)
    s_box = min(dw / bw, dh / bh)
    bands = s_cover > s_box * (1 + 1e-9)
    s = s_box if bands else s_cover

    def place(frame, img, b0, bl):
        if img <= frame:
            return (frame - img) / 2
        v = frame / 2 - (b0 + bl / 2) * s
        return min(0.0, max(frame - img, v))

    return {"s": s, "left": place(dw, mw * s, bx, bw), "top": place(dh, mh * s, by, bh),
            "bands": bands}


def box_for(m: dict, format_id: str) -> list[float]:
    return m["own"].get(format_id) or m["box"]


# -- reading the master --------------------------------------------------------


def master_file(job: dict, app: str) -> str:
    ext = "ai" if app == "ai" else "psd"
    return f"03_working/{job['id']}_master_v{job.get('version', 1):02d}.{ext}"


def take_preview(root: Path, src: Path) -> dict:
    """Stores her master's picture (exported by Illustrator/Photoshop, or
    dropped in by hand) as 02_assets/master/master.png in sRGB, plus a
    small JPG for the page. Returns {"preview", "pw", "ph"}."""
    from PIL import Image

    folder = root / PREVIEW_DIR
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.load()
        rgb = _to_srgb(im)
    dest = folder / PREVIEW_FILE
    tmp = dest.with_suffix(".tmp.png")
    rgb.save(tmp, "PNG", icc_profile=_srgb_bytes())
    tmp.replace(dest)
    small = rgb.copy()
    small.thumbnail((SMALL_SIDE, SMALL_SIDE))
    small.save(folder / PREVIEW_SMALL, "JPEG", quality=85)
    return {"preview": f"{PREVIEW_DIR}/{PREVIEW_FILE}", "small": f"{PREVIEW_DIR}/{PREVIEW_SMALL}",
            "pw": rgb.width, "ph": rgb.height}


def _srgb_bytes() -> bytes:
    from PIL import ImageCms

    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _to_srgb(im):
    from PIL import ImageCms

    icc = im.info.get("icc_profile")
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = _new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if "srgb" not in (ImageCms.getProfileDescription(src) or "").lower():
                return ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"),
                                                 outputMode="RGB")
        except Exception:  # noqa: BLE001 - an unreadable profile: take the pixels as they are
            pass
    return im.convert("RGB")


def _new(mode, size, color):
    from PIL import Image

    return Image.new(mode, size, color)


# -- the cut -------------------------------------------------------------------


def _hex(color: str | None) -> tuple[int, int, int]:
    c = (color or "#ffd400").lstrip("#")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 255, 212, 0


def render_size(master, dw: int, dh: int, box, fill: str, brand_color: str | None):
    """One digital size as a Pillow image, cut from the master's picture."""
    from PIL import Image, ImageFilter

    mw, mh = master.size
    f = fit(mw, mh, dw, dh, box)
    s = f["s"]
    if f["bands"] and fill == "blur":
        cs = max(dw / mw, dh / mh)
        cw, ch = dw / cs, dh / cs
        region = ((mw - cw) / 2, (mh - ch) / 2, (mw + cw) / 2, (mh + ch) / 2)
        small = (max(dw // 8, 1), max(dh // 8, 1))
        out = master.resize(small, Image.BILINEAR, box=region)
        out = out.filter(ImageFilter.GaussianBlur(max(min(small) / 25, 2)))
        out = out.resize((dw, dh), Image.BICUBIC)
    else:
        out = Image.new("RGB", (dw, dh), (255, 255, 255) if fill == "white" else _hex(brand_color))
    # only the part of the master the frame shows, resized once
    x0, y0 = max(0.0, -f["left"] / s), max(0.0, -f["top"] / s)
    x1, y1 = min(mw, (dw - f["left"]) / s), min(mh, (dh - f["top"]) / s)
    px0, py0 = round(f["left"] + x0 * s), round(f["top"] + y0 * s)
    pw = max(min(round((x1 - x0) * s), dw - px0), 1)
    ph = max(min(round((y1 - y0) * s), dh - py0), 1)
    part = master.resize((pw, ph), Image.LANCZOS, box=(x0, y0, x1, y1))
    out.paste(part, (px0, py0))
    return out


def _save(img, path: Path, kind: str, max_kb: float | None) -> None:
    tmp = path.with_name(path.stem + ".sh-tmp" + path.suffix)
    icc = _srgb_bytes()
    if kind == "jpg":
        for q in (92, 88, 84, 80, 75, 70, 65, 60):
            img.save(tmp, "JPEG", quality=q, icc_profile=icc, optimize=True)
            if not max_kb or tmp.stat().st_size / 1024 <= max_kb:
                break
    else:
        img.save(tmp, "PNG", icc_profile=icc, optimize=True)
    tmp.replace(path)


def digital_target(job: dict, fmt: dict, root: Path) -> Path:
    kind = _digital_type(fmt)
    d = next(d for d in job["deliverables"] if d["format_id"] == fmt["id"] and d["type"] == kind)
    return root / "04_export" / EXPORT_SUBDIR_BY_KIND[fmt["kind"]] / f"{d['expected_stem']}.{kind}"


def _ours(record: dict | None, path: Path) -> bool:
    if not path.exists():
        return True
    if not record:
        return False
    st = path.stat()
    return abs(st.st_mtime - record.get("mtime", 0)) < 1 and st.st_size == record.get("size")


def cut_digital(jobs_root: Path, job_id: str, overwrite: bool = False,
                report=None) -> dict:
    """Cuts every digital size from the master's picture into 04_export.
    A file there that the app didn't cut (she exported it herself) is
    kept unless `overwrite`. Returns {"made", "kept", "failed"}."""
    from PIL import Image

    job = job_mod.load_job(jobs_root, job_id)
    root = job_mod.job_path(jobs_root, job_id)
    m = section(job)
    if not m.get("preview") or not (root / m["preview"]).is_file():
        raise MasterError("Read the master first, so the app has its picture.")
    sizes = [f for f in cut_sizes(job, m["app"]) if f["kind"] != "print"]
    made, kept, failed, records = [], [], [], {}
    with Image.open(root / m["preview"]) as im:
        im.load()
        master = im.convert("RGB")
    for i, fmt in enumerate(sizes):
        if report:
            report(i, len(sizes), fmt.get("name", fmt["id"]))
        path = digital_target(job, fmt, root)
        rel = path.relative_to(root).as_posix()
        if not overwrite and not _ours(m["cuts"].get(fmt["id"]), path):
            kept.append({"format_id": fmt["id"], "file": rel})
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            img = render_size(master, int(fmt["size"]["w"]), int(fmt["size"]["h"]),
                              box_for(m, fmt["id"]), m["fill"], m.get("brand_color"))
            _save(img, path, _digital_type(fmt), fmt.get("max_kb"))
            st = path.stat()
            records[fmt["id"]] = {"at": time.time(), "file": rel, "mtime": st.st_mtime,
                                  "size": st.st_size}
            made.append({"format_id": fmt["id"], "file": rel})
        except OSError as exc:
            failed.append({"format_id": fmt["id"], "error": str(exc)})

    def change(job):
        section(job)["cuts"].update(records)

    job_mod.update_job(jobs_root, job_id, change)
    return {"made": made, "kept": kept, "failed": failed}


def print_cuts(job: dict) -> list[dict]:
    """What cut_master.jsx needs per print size: where the master goes in
    the frame (artboard + bleed), as fractions of that frame."""
    m = section(job)
    mw, mh = m.get("w"), m.get("h")
    if not mw or not mh:
        raise MasterError("Make the master first.")
    out = []
    for fmt in cut_sizes(job, m["app"]):
        if fmt["kind"] != "print":
            continue
        dw, dh = frame_of(fmt)
        f = fit(mw, mh, dw, dh, box_for(m, fmt["id"]))
        bleed = (fmt.get("bleed_mm") or 0) * (fmt.get("scale") or 1)
        out.append({"format_id": fmt["id"], "bleed_mm": bleed,
                    "x": f["left"] / dw, "y": f["top"] / dh, "w": mw * f["s"] / dw,
                    "h": mh * f["s"] / dh, "bands": f["bands"]})
    return out


def view(job: dict, root: Path) -> dict:
    """Everything the page shows."""
    m = section(job)
    app = m["app"]
    try:
        plan = master_size(job, app)
    except MasterError as exc:
        plan = {"error": str(exc)}
    sizes = []
    for fmt in cut_sizes(job, app):
        dw, dh = frame_of(fmt)
        row = {"format_id": fmt["id"], "name": fmt.get("name", fmt["id"]), "kind": fmt["kind"],
               "w": fmt["size"]["w"], "h": fmt["size"]["h"],
               "unit": "mm" if fmt["kind"] == "print" else "px", "fw": dw, "fh": dh,
               "own": fmt["id"] in m["own"], "box": box_for(m, fmt["id"]),
               "cut": m["cuts"].get(fmt["id"])}
        if fmt["kind"] == "print":
            row["dest"] = "Placed in your Illustrator print file, linked to the master"
        else:
            p = digital_target(job, fmt, root)
            row["dest"] = p.relative_to(root).as_posix()
            row["exists"] = p.exists()
            row["theirs"] = p.exists() and not _ours(m["cuts"].get(fmt["id"]), p)
        sizes.append(row)
    master_path = root / m["file"] if m.get("file") else None
    return {
        "mode": m["mode"], "app": app, "file": m.get("file"),
        "file_exists": bool(master_path and master_path.exists()),
        "w": m.get("w"), "h": m.get("h"), "plan": plan,
        "preview": m.get("preview"), "small": m.get("small"), "pw": m.get("pw"),
        "ph": m.get("ph"), "read_at": m.get("read_at"),
        "box": m["box"], "fill": m["fill"], "brand_color": m.get("brand_color"),
        "sizes": sizes,
        "left_out": [{"format_id": f["id"], "name": f.get("name", f["id"]), "kind": f["kind"],
                      "why": "panels" if f.get("panels") else "print" if f["kind"] == "print"
                      else "type"} for f in left_out(job, app)],
        "has_print_file": bool(job_mod.current_print_files(job)),
    }


# -- changes -------------------------------------------------------------------


def update(jobs_root: Path, job_id: str, *, mode=None, app=None, box=None, format_id=None,
           reset=False, fill=None, brand_color=None) -> dict:
    if mode is not None and mode not in MODES:
        raise MasterError("Design each size, or one master.")
    if app is not None and app not in APPS:
        raise MasterError("The master is in Illustrator or Photoshop.")
    if fill is not None and fill not in FILLS:
        raise MasterError("Around the picture: blur, brand colour or white.")
    if brand_color is not None and not (isinstance(brand_color, str) and len(brand_color) == 7
                                        and brand_color[0] == "#"):
        raise MasterError("The brand colour is #rrggbb.")
    clean = clean_box(box) if box is not None else None

    def change(job):
        m = section(job)
        if mode is not None:
            m["mode"] = mode
        if app is not None and app != m["app"]:
            if m.get("file"):
                raise MasterError("This job's master is already made. Start a revision to make "
                                  "a new one in the other app.")
            m["app"] = app
        if format_id and reset:
            m["own"].pop(format_id, None)
        elif clean is not None:
            if format_id:
                m["own"][format_id] = clean
            else:
                m["box"] = clean
        if fill is not None:
            m["fill"] = fill
        if brand_color is not None:
            m["brand_color"] = brand_color

    return job_mod.update_job(jobs_root, job_id, change)


def record_made(jobs_root: Path, job_id: str, rel: str, w: int, h: int) -> dict:
    def change(job):
        m = section(job)
        m.update(file=rel, w=w, h=h)

    return job_mod.update_job(jobs_root, job_id, change)


def record_preview(jobs_root: Path, job_id: str, info: dict) -> dict:
    def change(job):
        section(job).update(info, read_at=time.time())

    return job_mod.update_job(jobs_root, job_id, change)


def record_print_cuts(jobs_root: Path, job_id: str, cut: list[dict]) -> dict:
    def change(job):
        cuts = section(job)["cuts"]
        for c in cut:
            cuts[c["format_id"]] = {"at": time.time(), "file": Path(c["file"]).name}

    return job_mod.update_job(jobs_root, job_id, change)
