"""Job creation and lifecycle (SPEC.md §6.1). Python is the sole
writer of job.json -- the JSX/Figma adapters only ever receive it and
report results back (SPEC.md §4 design principles)."""

from __future__ import annotations

import functools
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from studio_helper import paths
from studio_helper.core import naming, scaffold
from studio_helper.core.registry import Registry

SCHEMA_VERSION = 1


class JobError(Exception):
    pass


# Every job.json change is load -> modify -> write. Requests run on
# separate threads, so two at once (a double-clicked "Start revision")
# would both read v02 and both write v03. One lock for all of them is
# plenty for one person's jobs.
_write_lock = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _write_lock:
            return fn(*args, **kwargs)
    return wrapper


def _now_local() -> datetime:
    return datetime.now().astimezone()


PRINT_TYPES = ("pdf", "tiff")


def _exports_for_size(fmt: dict, w: float, h: float) -> list[str]:
    """`exports` lists what a format may be delivered as. When a print
    format allows both PDF and TIFF, the physical size picks one: TIFF
    over `tiff_if_longest_side_mm_over`, else PDF (SPEC.md §6.4 step 2)."""
    exports = fmt.get("exports", [])
    if fmt.get("kind") != "print" or not all(t in exports for t in PRINT_TYPES):
        return list(exports)
    threshold = fmt.get("tiff_if_longest_side_mm_over")
    drop = "pdf" if threshold and max(w, h) > threshold else "tiff"
    return [t for t in exports if t != drop]


def _deliverables_for(date_str: str, slug: str, fmt: dict, version: int) -> list[dict]:
    panels = fmt.get("panels")
    unit = fmt.get("unit") or fmt["size"]["unit"]
    deliverables = []

    def add(w: float, h: float, panel_index: int | None) -> None:
        for export_type in _exports_for_size(fmt, w, h):
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


@_locked
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


# Format fields that change no size or file name, so existing jobs follow
# the registry for them.
REFRESHED_KEYS = ("tiff_ppi", "max_kb", "max_duration_s", "fps", "audio", "ui_safe_px")


@_locked
def refresh_from_registry(jobs_root: Path, job_id: str, registry: Registry,
                          keys: tuple[str, ...] = REFRESHED_KEYS) -> dict:
    """Export and check settings that don't change a job's sizes or
    file names (TIFF resolution, video limits) follow the current
    registry, so a fix there reaches jobs that already exist."""
    job = load_job(jobs_root, job_id)
    changed = False
    for fmt in job["formats"]:
        current = registry.formats.get(fmt["id"])
        if not current:
            continue
        for key in keys:
            if key in current and fmt.get(key) != current[key]:
                fmt[key] = current[key]
                changed = True
    if changed:
        _write_job(job_path(jobs_root, job_id), job)
    return job


def _resolve_formats(registry: Registry, format_ids: list[str],
                     bleed_overrides: dict | None, custom_formats: list[dict]) -> list[dict]:
    """Fully resolved copies (incl. defaults) so a job stays stable even
    if registry.yaml changes later (SPEC.md §6.1 job.json), with the
    print shop's per-job bleed applied and oversize print auto-scaled."""
    formats_resolved = [dict(registry.formats[fid]) for fid in format_ids]
    formats_resolved += [dict(f) for f in custom_formats]
    for fmt in formats_resolved:
        override = (bleed_overrides or {}).get(fmt["id"])
        if override is not None and fmt["kind"] == "print":
            try:
                bleed = float(override)
            except (TypeError, ValueError) as exc:
                raise JobError(f"Bleed for '{fmt['name']}' must be a number.") from exc
            if bleed < 0:
                raise JobError(f"Bleed for '{fmt['name']}' can't be negative.")
            fmt["bleed_mm"] = int(bleed) if bleed == int(bleed) else bleed
    return [_auto_scale(f) for f in formats_resolved]


def create_job(
    jobs_root: Path,
    registry: Registry,
    name: str,
    format_ids: list[str],
    now: datetime | None = None,
    bleed_overrides: dict[str, float] | None = None,
    custom_formats: list[dict] | None = None,
) -> dict:
    """`bleed_overrides` maps a format id to the bleed (mm) the print
    shop asked for on this job. `custom_formats` are already-resolved
    one-off formats (core.custom_formats) that aren't in the registry."""
    custom_formats = custom_formats or []
    if not name or not name.strip():
        raise JobError("Job name cannot be empty.")
    if not format_ids and not custom_formats:
        raise JobError("Select at least one format.")

    unknown = [fid for fid in format_ids if fid not in registry.formats]
    if unknown:
        raise JobError(f"Unknown format id(s): {', '.join(unknown)}")
    # Everything is checked before the folder is made, so a bad bleed
    # value can't leave a half-made job behind.
    formats_resolved = _resolve_formats(registry, format_ids, bleed_overrides, custom_formats)

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


@_locked
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


@_locked
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


_VERSION_SUFFIX = re.compile(r"_v(\d+)$")


def file_version(rel_path: str) -> int | None:
    """2 for ".../x_print_part1_v02.ai"; None without a _vNN suffix."""
    m = _VERSION_SUFFIX.search(Path(rel_path).stem)
    return int(m.group(1)) if m else None


def current_print_files(job: dict) -> list[str]:
    """The Illustrator files to check and export: only the newest set.
    files.print keeps every .ai ever created for the job, one set per
    "Create Illustrator file" (v01, v03, ...). Exporting all of them
    gave each one the current version's export names, so older
    artwork overwrote the current one. The newest set is the one with
    the highest _vNN, which may be older than the job's version: she
    can keep working in the same file across revisions."""
    files = job["files"].get("print") or []
    versions = [v for v in (file_version(f) for f in files) if v is not None]
    if not versions:
        return list(files)
    newest = max(versions)
    return [f for f in files if file_version(f) == newest]


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


@_locked
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


def _job_date(job: dict) -> str:
    return datetime.fromisoformat(job["created"]).strftime("%Y-%m-%d")


@_locked
def add_formats(
    jobs_root: Path,
    job_id: str,
    registry: Registry,
    format_ids: list[str],
    bleed_overrides: dict[str, float] | None = None,
    custom_formats: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """'Add sizes' (ROADMAP R2): a campaign gets extended to a new mall
    after it was made, often after delivery. The new formats join the
    job at its current version -- this isn't a revision -- and what was
    already delivered is left as it is. Recorded as a numbered batch,
    which names the add-on Illustrator file and the "added" label."""
    custom_formats = custom_formats or []
    job = load_job(jobs_root, job_id)
    have = {f["id"] for f in job["formats"]}
    if not format_ids and not custom_formats:
        raise JobError("Select at least one size to add.")
    already = [fid for fid in format_ids if fid in have]
    if already:
        names = ", ".join(registry.formats[f]["name"] if f in registry.formats else f
                          for f in already)
        raise JobError(f"Already in this job: {names}.")
    unknown = [fid for fid in format_ids if fid not in registry.formats]
    if unknown:
        raise JobError(f"Unknown format id(s): {', '.join(unknown)}")
    clash = [f["id"] for f in custom_formats if f["id"] in have]
    if clash:
        raise JobError(f"A size with this id is already in the job: {', '.join(clash)}")

    added = _resolve_formats(registry, format_ids, bleed_overrides, custom_formats)
    date_str = _job_date(job)
    for fmt in added:
        job["formats"].append(fmt)
        job["deliverables"].extend(_deliverables_for(date_str, job["slug"], fmt, job["version"]))
    ids = [f["id"] for f in added]
    batches = job.setdefault("added", [])
    batches.append({
        "batch": len(batches) + 1,
        "at": (now or _now_local()).isoformat(timespec="seconds"),
        "format_ids": ids,
    })
    # adding back something removed earlier: it's no longer "removed"
    job["removed"] = [r for r in job.get("removed", []) if r["format"]["id"] not in ids]
    _write_job(job_path(jobs_root, job_id), job)
    return job


@_locked
def remove_format(jobs_root: Path, job_id: str, format_id: str,
                  now: datetime | None = None) -> dict:
    """A placement was cancelled: the format stops being expected. Only
    job.json changes -- her artboards and exported files stay where
    they are, and restore_format brings it back."""
    job = load_job(jobs_root, job_id)
    fmt = next((f for f in job["formats"] if f["id"] == format_id), None)
    if fmt is None:
        raise JobError("That size isn't in this job.")
    if len(job["formats"]) == 1:
        raise JobError("A job needs at least one size. Delete the job instead.")
    job["formats"] = [f for f in job["formats"] if f["id"] != format_id]
    job["deliverables"] = [d for d in job["deliverables"] if d["format_id"] != format_id]
    job.setdefault("removed", []).append({
        "at": (now or _now_local()).isoformat(timespec="seconds"),
        "format": fmt,
    })
    _write_job(job_path(jobs_root, job_id), job)
    return job


@_locked
def restore_format(jobs_root: Path, job_id: str, format_id: str) -> dict:
    job = load_job(jobs_root, job_id)
    entry = next((r for r in job.get("removed", []) if r["format"]["id"] == format_id), None)
    if entry is None:
        raise JobError("Nothing to restore for that size.")
    fmt = entry["format"]
    job["formats"].append(fmt)
    job["deliverables"].extend(_deliverables_for(_job_date(job), job["slug"], fmt, job["version"]))
    job["removed"] = [r for r in job["removed"] if r is not entry]
    _write_job(job_path(jobs_root, job_id), job)
    return job


def print_set_version(job: dict) -> int:
    """The _vNN of the Illustrator set she works in now, which can be
    older than the job's version (she keeps working in the same file
    across revisions). An add-on file must carry this number, not the
    job's: with a higher one, current_print_files would pick only the
    add-on and check/export would skip her real artwork."""
    versions = [v for v in (file_version(f) for f in current_print_files(job)) if v is not None]
    return max(versions) if versions else job["version"]


def add_batch(job: dict, batch: int) -> dict | None:
    return next((b for b in job.get("added", []) if b["batch"] == batch), None)


@_locked
def update_job(jobs_root: Path, job_id: str, change) -> dict:
    """Applies change(job) -> None under the job lock and saves. For the
    job's own sections (video, brand pieces, dates, deliveries); Python
    stays the only writer of job.json."""
    job = load_job(jobs_root, job_id)
    change(job)
    _write_job(job_path(jobs_root, job_id), job)
    return job


# "<job id>_print[_add01][_bleed3mm][_part2]_v03.ai" / "<job id>_digital_v02.psd"
_JOB_FILE_NAME = re.compile(
    r"^(?P<prefix>.+?)(?P<rest>_(?:print|digital)(?:_.*?)?)_v\d+(?P<ext>\.\w+)$")


def reuse_job(jobs_root: Path, registry: Registry, source_id: str, name: str,
              keep_ids: list[str], new_ids: list[str] | None = None,
              custom_formats: list[dict] | None = None, now: datetime | None = None) -> dict:
    """'Reuse as new job' (ROADMAP R8): the same campaign with a new offer
    or dates. A new job starts from copies of the old one's current
    working files (renamed to the new job, _v01), its video masters and
    brand pieces. The old job and its files are never changed."""
    source = load_job(jobs_root, source_id)
    src_root = job_path(jobs_root, source_id)
    kept = [dict(f) for f in source["formats"] if f["id"] in keep_ids]
    new_ids = [i for i in (new_ids or []) if i not in keep_ids]
    job = create_job(jobs_root, registry, name, new_ids, now=now,
                     custom_formats=kept + list(custom_formats or []))
    root = job_path(jobs_root, job["id"])

    def renamed(rel: str) -> str:
        p = Path(rel)
        m = _JOB_FILE_NAME.match(p.name)
        new_name = f"{job['id']}{m.group('rest')}_v01{m.group('ext')}" if m else p.name
        return (p.parent / new_name).as_posix()

    files = {"print": [], "psd": None}
    for rel in current_print_files(source):
        if (src_root / rel).is_file():
            dest = renamed(rel)
            shutil.copy2(src_root / rel, root / dest)
            files["print"].append(dest)
    if source["files"].get("psd") and (src_root / source["files"]["psd"]).is_file():
        dest = renamed(source["files"]["psd"])
        shutil.copy2(src_root / source["files"]["psd"], root / dest)
        files["psd"] = dest
    for folder in ("02_assets/video", "02_assets/pieces", "02_assets/motion-b"):
        if (src_root / folder).is_dir():
            shutil.copytree(src_root / folder, root / folder, dirs_exist_ok=True)

    def change(j):
        j["files"] = files
        j["source_job"] = source_id
        if source.get("pieces"):
            j["pieces"] = [dict(p) for p in source["pieces"]]
        video = source.get("video")
        if video:
            keep = {f["id"] for f in j["formats"]}
            j["video"] = {k: v for k, v in video.items() if k != "renders"}
            j["video"]["screens"] = {k: v for k, v in video.get("screens", {}).items()
                                     if k in keep}
            j["video"]["renders"] = {}

    return update_job(jobs_root, job["id"], change)


DATE_KEYS = ("print_due", "digital_due", "live_from", "live_to")


def clean_dates(raw: dict) -> dict:
    """Campaign dates from her brief (R11) as ISO dates; empty ones dropped."""
    out = {}
    for key in DATE_KEYS:
        value = str(raw.get(key) or "").strip()
        if not value:
            continue
        try:
            out[key] = datetime.fromisoformat(value).date().isoformat()
        except ValueError as exc:
            raise JobError(f"'{value}' isn't a date (use YYYY-MM-DD).") from exc
    return out


def next_due(job: dict, today: str | None = None) -> dict | None:
    """The nearest print/digital due date still ahead (or today), for the
    Jobs list badge: {"what": "print", "date": "..."}."""
    today = today or datetime.now().date().isoformat()
    dates = job.get("dates") or {}
    upcoming = sorted((d, k.split("_")[0]) for k, d in dates.items()
                      if k.endswith("_due") and d >= today)
    return {"what": upcoming[0][1], "date": upcoming[0][0]} if upcoming else None


def mark_batch_applied(jobs_root: Path, job_id: str, batch: int, app: str) -> dict:
    """Remembers that a batch of added sizes is now in her print or
    digital files, so the job page stops offering to add it."""
    def change(job):
        b = add_batch(job, batch)
        if b is not None and app not in b.setdefault("applied", []):
            b["applied"].append(app)
    return update_job(jobs_root, job_id, change)
