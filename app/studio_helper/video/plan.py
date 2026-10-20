"""Which master videos to generate in Higgsfield for a job (ROADMAP R4).

Higgsfield makes a handful of shapes (16:9, 4:3, 1:1, 3:4, 9:16, nothing
taller). Each screen gets the shape that keeps the most of the picture
after a cover crop; screens no shape covers well (tall strips) are
flagged, so she can reframe them in Higgsfield or use fill.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND

MASTER_RATIOS = (("16:9", 16 / 9), ("4:3", 4 / 3), ("1:1", 1.0), ("3:4", 3 / 4), ("9:16", 9 / 16))
STRIP_BELOW = 0.70  # a screen keeping less of the best master than this is a strip
UPSCALE_WARN = 1.5


def video_formats(job: dict) -> list[dict]:
    return [f for f in job["formats"] if "mp4" in f.get("exports", []) and "size" in f]


def coverage(master_ratio: float, screen_ratio: float) -> float:
    """Share of the master still visible on the screen after a cover crop."""
    return min(master_ratio / screen_ratio, screen_ratio / master_ratio)


def _even_up(v: float) -> int:
    n = math.ceil(v)
    return n + (n % 2)


def video_plan(job: dict) -> dict:
    """{"masters": [{ratio, min_w, min_h, screens: [{id, name, keeps}]}],
        "strips": [{id, name, ratio, keeps}]}"""
    groups: dict[str, dict] = {}
    strips = []
    for fmt in video_formats(job):
        w, h = fmt["size"]["w"], fmt["size"]["h"]
        r = w / h
        label, mr = max(MASTER_RATIOS, key=lambda m: coverage(m[1], r))
        keeps = coverage(mr, r)
        entry = {"id": fmt["id"], "name": fmt.get("name", fmt["id"]), "keeps": round(keeps, 3)}
        group = groups.setdefault(label, {"ratio": label, "_r": mr, "min_w": 0, "screens": []})
        group["screens"].append(entry)
        # the master needs at least the screen's pixels after the cover scale
        group["min_w"] = max(group["min_w"], w, h * mr)
        if keeps < STRIP_BELOW:
            strips.append(dict(entry, ratio=label))
    masters = []
    for label, _r in MASTER_RATIOS:
        g = groups.get(label)
        if not g:
            continue
        min_w = _even_up(g.pop("min_w"))
        r = g.pop("_r")
        masters.append(dict(g, min_w=min_w, min_h=_even_up(min_w / r)))
    return {"masters": masters, "strips": strips}


def upscale_warnings(master_w: int, master_h: int, job: dict) -> list[str]:
    """Screens the attached master is too small for (R4)."""
    warnings = []
    for fmt in video_formats(job):
        dw, dh = fmt["size"]["w"], fmt["size"]["h"]
        s = max(dw / master_w, dh / master_h)
        if s > UPSCALE_WARN:
            need_w, need_h = _even_up(master_w * s), _even_up(master_h * s)
            warnings.append(
                f"{fmt.get('name', fmt['id'])} needs a bigger master: upscale it in Higgsfield "
                f"to at least {need_w} × {need_h}."
            )
    return warnings


def readme_text(job: dict, plan: dict) -> str:
    lines = [f"Higgsfield plan for: {job.get('name', job['id'])}", ""]
    if not plan["masters"]:
        lines.append("This job has no video sizes.")
    for m in plan["masters"]:
        lines.append(f"Generate a {m['ratio']} video, at least {m['min_w']} x {m['min_h']} px.")
        for s in m["screens"]:
            lines.append(f"  - {s['name']} (keeps {round(s['keeps'] * 100)}% of the picture)")
        lines.append("")
    if plan["strips"]:
        lines.append("Tall strips: no Higgsfield shape fits these well. Reframe the video for")
        lines.append("them in Higgsfield, or let Studio Helper fill the sides (blur or black):")
        for s in plan["strips"]:
            lines.append(f"  - {s['name']} (only {round(s['keeps'] * 100)}% from {s['ratio']})")
        lines.append("")
    limits = [f for f in video_formats(job) if f.get("max_duration_s")]
    if limits:
        lines.append("Length limits:")
        for f in limits:
            lines.append(f"  - {f.get('name', f['id'])}: {f['max_duration_s']:g} s at most")
        lines.append("")
    lines.append("Screens play without sound; stories and posts keep it.")
    return "\r\n".join(lines) + "\r\n"


def make_reference_pack(job: dict, job_root: Path) -> tuple[Path, list[str]]:
    """Copies the job's static exports for its video sizes and its brand
    pieces into 02_assets/higgsfield/, with a README of the plan. Only
    copies: her files are never moved or changed. Returns the folder and
    the names copied."""
    pack = job_root / "02_assets" / "higgsfield"
    pack.mkdir(parents=True, exist_ok=True)
    copied = []
    video_ids = {f["id"] for f in video_formats(job)}
    kinds = {f["id"]: f["kind"] for f in job["formats"]}
    for d in job["deliverables"]:
        if d["format_id"] not in video_ids or d["type"] not in ("png", "jpg"):
            continue
        src = (job_root / "04_export" / EXPORT_SUBDIR_BY_KIND[kinds[d["format_id"]]]
               / f"{d['expected_stem']}.{d['type']}")
        if src.is_file():
            shutil.copy2(src, pack / src.name)
            copied.append(src.name)
    for piece in job.get("pieces", []):
        src = job_root / piece["file"]
        if src.is_file():
            shutil.copy2(src, pack / src.name)
            copied.append(src.name)
    (pack / "README.txt").write_text(readme_text(job, video_plan(job)), encoding="utf-8")
    return pack, copied
