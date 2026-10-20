"""The delivery package for her manager (ROADMAP R10).

She hands finished files to her manager, who sends them on (malls, ad
operators, print shops). One ZIP per job -- or per batch of sizes added
later -- with only the current files that passed their checks, a folder
per format group (so each folder can go to whoever needs it), and a
README listing every file with its print-shop notes. Copies only: her
exports are never moved, and deleting a package deletes nothing else.
"""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.core.registry import default_group
from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND

DELIVERY_DIR = "05_delivery"


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_.()" else "-" for c in name).strip() or "Other"


def candidates(job: dict, rows: list[dict], root: Path, batch: int | None = None,
               include_warn: bool = False) -> list[dict]:
    """Every current deliverable with what will happen to it in a package:
    {"row", "path", "group", "include", "why"}."""
    fmts = {f["id"]: f for f in job["formats"]}
    only = None
    if batch is not None:
        b = job_mod.add_batch(job, batch)
        only = set(b["format_ids"]) if b else set()
    out = []
    for row in rows:
        fmt = fmts.get(row["format_id"])
        if fmt is None or (only is not None and row["format_id"] not in only):
            continue
        path = (root / "04_export" / EXPORT_SUBDIR_BY_KIND[fmt["kind"]]
                / f"{row['expected_stem']}.{row['type']}")
        status = row["status"]
        if status == "missing" or not path.is_file():
            include, why = False, "Not exported yet."
        elif status == "fail":
            include, why = False, "Fails its checks."
        elif status == "warn" and not include_warn:
            include, why = False, "Has warnings: tick \"send anyway\" to include it."
        else:
            include, why = True, ""
        out.append({"row": row, "path": path, "include": include, "why": why,
                    "group": fmt.get("group") or default_group(fmt),
                    "name": fmt.get("name", fmt["id"]), "notes": fmt.get("notes", "")})
    return out


def make_package(jobs_root: Path, job_id: str, rows: list[dict], batch: int | None = None,
                 include_warn: bool = False, now: float | None = None) -> dict:
    job = job_mod.load_job(jobs_root, job_id)
    root = job_mod.job_path(jobs_root, job_id)
    items = [c for c in candidates(job, rows, root, batch, include_warn) if c["include"]]
    if not items:
        raise job_mod.JobError("Nothing is ready to send yet: no file has passed its checks.")
    stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(now))
    suffix = f"_add{batch:02d}" if batch is not None else ""
    folder = root / DELIVERY_DIR
    folder.mkdir(exist_ok=True)
    zip_path = folder / f"{job['id']}{suffix}_{stamp}.zip"
    readme = [f"{job['name']} -- files for delivery", f"Packed {stamp.replace('_', ' ')}", ""]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for group in dict.fromkeys(c["group"] for c in items):
            readme.append(f"{group}/")
            for c in (c for c in items if c["group"] == group):
                arc = f"{_safe(group)}/{c['path'].name}"
                # pictures and video are already compressed: store them as they are
                kind = zipfile.ZIP_STORED if c["path"].suffix.lower() in (
                    ".png", ".jpg", ".jpeg", ".mp4", ".pdf") else zipfile.ZIP_DEFLATED
                z.write(c["path"], arc, compress_type=kind)
                size = c["path"].stat().st_size / 1024 / 1024
                line = f"  {c['path'].name}  ({c['name']}, {size:.1f} MB)"
                readme.append(line)
                if c["notes"]:
                    readme.append(f"      Notes: {c['notes']}")
            readme.append("")
        z.writestr("README.txt", "\r\n".join(readme) + "\r\n")
    record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
              "zip": zip_path.relative_to(root).as_posix(),
              "files": [c["path"].name for c in items], "batch": batch}
    job_mod.update_job(jobs_root, job_id,
                       lambda j: j.setdefault("deliveries", []).append(record))
    return record
