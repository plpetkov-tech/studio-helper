"""Studio Helper for AI assistants (ROADMAP R12): `python -m studio_helper --mcp`.

She already drives Concat from the ChatGPT desktop app over MCP; this
lets the same assistant see and use Studio Helper, so every feature is
reachable by asking ("what's left on Black November?", "add the Mall X
size", "make the LED videos black instead of blur").

It is a thin client of the *running* app's local HTTP API -- it never
reads or writes job.json itself, so the app stays the only writer. It
finds the app through instance.json (port + per-launch token), and starts
the app in the background if it isn't running.

Never exposed: deleting jobs or formats, updating, quitting, or any file's
contents. Tools return names and statuses only, never artwork.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from studio_helper import __version__, config, instance

PROTOCOL_VERSION = "2025-06-18"
TASK_TIMEOUT_S = 900


class ToolError(Exception):
    pass


# -- talking to the running app ---------------------------------------------------


def _app() -> instance.InstanceInfo:
    info = instance.read()
    if info is not None and instance.is_alive(info):
        return info
    _start_app()
    deadline = time.time() + 30
    while time.time() < deadline:
        info = instance.read()
        if info is not None and instance.is_alive(info):
            return info
        time.sleep(0.5)
    raise ToolError("Studio Helper didn't start. Open it from the desktop shortcut, "
                    "then ask again.")


def _start_app() -> None:
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    cmd = [str(windowless if windowless.exists() else exe), "-m", "studio_helper", "--background"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(cmd, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def api(method: str, path: str, body: dict | None = None, timeout: float = 60) -> dict:
    info = _app()
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{info.port}{path}", data=data, method=method,
        headers={"X-Studio-Helper-Token": info.token, "Host": f"127.0.0.1:{info.port}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read()).get("error")
        except ValueError:
            msg = None
        raise ToolError(msg or f"Studio Helper answered {exc.code}.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ToolError("Couldn't reach Studio Helper. Is it open?") from exc


def _wait(task_id: str) -> dict:
    deadline = time.time() + TASK_TIMEOUT_S
    while time.time() < deadline:
        t = api("GET", f"/api/tasks/{task_id}")
        if t["status"] == "done":
            return t["result"]
        if t["status"] == "error":
            raise ToolError(t.get("error") or "The task failed.")
        time.sleep(1)
    raise ToolError("Still working after 15 minutes; check the job page in Studio Helper.")


def _task(path: str, body: dict | None = None) -> dict:
    return _wait(api("POST", path, body or {})["task_id"])


# -- the tools -------------------------------------------------------------------------


def _job_summary(job: dict, deliverables: list[dict]) -> dict:
    return {
        "id": job["id"], "name": job["name"], "version": job["version"],
        "dates": job.get("dates", {}),
        "sizes": [{"id": f["id"], "name": f.get("name"), "kind": f["kind"],
                   "size": f.get("size"), "exports": f.get("exports"),
                   "notes": f.get("notes") or None} for f in job["formats"]],
        "deliverables": [{"file": f"{d['expected_stem']}.{d['type']}", "format_id": d["format_id"],
                          "status": d["status"],
                          "problems": [c["message"] for c in d.get("checks", [])
                                       if c["status"] in ("warn", "fail")]}
                         for d in deliverables],
        "added_batches": job.get("added", []),
        "removed": [r["format"]["id"] for r in job.get("removed", [])],
        "print_files": job["files"].get("print", []), "psd": job["files"].get("psd"),
        "based_on": job.get("source_job"),
    }


def _s(type_: str, desc: str, **extra) -> dict:
    return {"type": type_, "description": desc, **extra}


JOB_ID = _s("string", "Job id from jobs_list (e.g. 2026-10-20_black-november).")
FORMAT_IDS = _s("array", "Format ids from formats_list.", items={"type": "string"})

TOOLS: dict[str, dict] = {}


def tool(name: str, description: str, props: dict | None = None, required: list[str] | None = None):
    def deco(fn):
        TOOLS[name] = {"fn": fn, "schema": {
            "name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props or {},
                            "required": required or []}}}
        return fn
    return deco


@tool("jobs_list", "Every job, newest first: name, how many files are delivered of how many, "
      "next due date.")
def jobs_list(a):
    return {"jobs": [{k: j.get(k) for k in ("id", "name", "created", "version", "deliverables_done",
                                            "deliverables_total", "counts", "next_due", "dates")}
                     for j in api("GET", "/api/jobs")["jobs"]]}


@tool("job_get", "One job in full: its sizes, every expected file with its check status "
      "(ok / warn / fail / missing) and the problems found, working files, dates.",
      {"job_id": JOB_ID}, ["job_id"])
def job_get(a):
    data = api("GET", f"/api/jobs/{a['job_id']}")
    return _job_summary(data["job"], data["deliverables"])


@tool("formats_list", "Every format (size) in the registry, grouped: id, name, kind, size, "
      "delivery types, notes, whether the size is still an estimate, and the presets.")
def formats_list(a):
    reg = api("GET", "/api/registry")
    keep = ("id", "name", "group", "kind", "size", "panels", "exports", "notes", "estimated",
            "source", "max_duration_s", "max_kb", "bleed_mm")
    return {"formats": [{k: f[k] for k in keep if k in f} for f in reg.get("formats", [])],
            "presets": reg.get("job_types", {})}


@tool("setup_check", "Checks that Illustrator, Photoshop, the Figma plugin, the PDF preset and "
      "Concat are ready.")
def setup_check(a):
    checks = _task("/api/setup-check")
    concat = api("GET", "/api/concat/status", timeout=60).get("concat")
    return {"checks": checks, "concat": concat}


@tool("job_create", "Creates a job: name, format ids (and/or a preset), optional dates "
      "{print_due, digital_due, live_from, live_to} as YYYY-MM-DD and per-size bleed in mm.",
      {"name": _s("string", "Job name, e.g. the campaign name."), "format_ids": FORMAT_IDS,
       "job_type": _s("string", "A preset name instead of format_ids."),
       "dates": _s("object", "Due dates from the brief."),
       "bleed_overrides": _s("object", "{format_id: bleed in mm} when the print shop asks.")},
      ["name"])
def job_create(a):
    return {"job": api("POST", "/api/jobs", a)["job"]["id"]}


@tool("job_add_sizes", "Adds sizes to an existing job, even a delivered one (e.g. a new mall "
      "signed the campaign). They join at the current version. Then call print_setup / "
      "digital_setup with the returned batch to add them to her files.",
      {"job_id": JOB_ID, "format_ids": FORMAT_IDS,
       "bleed_overrides": _s("object", "{format_id: bleed in mm}")}, ["job_id", "format_ids"])
def job_add_sizes(a):
    data = api("POST", f"/api/jobs/{a['job_id']}/formats", a)
    return {"batch": data["batch"]}


@tool("job_remove_size", "Stops expecting one size in a job (a cancelled placement). Her files "
      "are untouched; job_restore_size brings it back.",
      {"job_id": JOB_ID, "format_id": _s("string", "The size to remove.")},
      ["job_id", "format_id"])
def job_remove_size(a):
    api("POST", f"/api/jobs/{a['job_id']}/formats/{a['format_id']}/remove", {})
    return {"removed": a["format_id"]}


@tool("job_restore_size", "Brings back a size removed from a job.",
      {"job_id": JOB_ID, "format_id": _s("string", "The size to restore.")},
      ["job_id", "format_id"])
def job_restore_size(a):
    api("POST", f"/api/jobs/{a['job_id']}/formats/{a['format_id']}/restore", {})
    return {"restored": a["format_id"]}


@tool("job_start_revision", "Starts the next revision (v02, v03...): new exports get the new "
      "version; she keeps working in the same files.", {"job_id": JOB_ID}, ["job_id"])
def job_start_revision(a):
    return {"version": api("POST", f"/api/jobs/{a['job_id']}/revision", {})["job"]["version"]}


@tool("job_set_dates", "Sets the brief's dates on a job (YYYY-MM-DD).",
      {"job_id": JOB_ID, "print_due": _s("string", ""), "digital_due": _s("string", ""),
       "live_from": _s("string", ""), "live_to": _s("string", "")}, ["job_id"])
def job_set_dates(a):
    return {"dates": api("POST", f"/api/jobs/{a['job_id']}/dates", a)["job"]["dates"]}


@tool("job_reuse", "Same campaign, new offer: a new job from copies of this job's working "
      "files. keep = this job's sizes to carry over; format_ids = sizes to add.",
      {"job_id": JOB_ID, "name": _s("string", "New job name."), "keep": FORMAT_IDS,
       "format_ids": FORMAT_IDS}, ["job_id", "name"])
def job_reuse(a):
    return {"job": api("POST", f"/api/jobs/{a['job_id']}/reuse", a)["job"]["id"]}


@tool("format_add", "Adds a new size to Formats (e.g. from an operator's spec sheet): name, "
      "kind (print/screen/social/web), w and h (mm for print, px otherwise), export type, "
      "group, notes.",
      {"name": _s("string", ""), "kind": _s("string", ""), "w": _s("number", ""),
       "h": _s("number", ""), "export": _s("string", "tiff/pdf for print; png/jpg/mp4 else"),
       "group": _s("string", ""), "notes": _s("string", "The operator's requirements.")},
      ["name", "kind", "w", "h"])
def format_add(a):
    return {"format": api("POST", "/api/registry/formats", a)["format"]["id"]}


@tool("format_update", "Changes a size in Formats: name, group, notes, w/h, bleed_mm, safe_mm, "
      "exports, tiff_ppi, max_duration_s, max_mb, source, estimated.",
      {"format_id": _s("string", ""), "changes": _s("object", "Only the fields to change.")},
      ["format_id", "changes"])
def format_update(a):
    data = api("POST", f"/api/registry/formats/{a['format_id']}", a["changes"])
    return {"format": data["format"]}


def _adobe(path: str, a: dict) -> dict:
    result = _task(path, {k: v for k, v in a.items() if k != "job_id"})
    return {"ok": result.get("ok"), "data": result.get("data"),
            "errors": result.get("errors"), "warnings": result.get("warnings")}


BATCH = _s("integer", "Only the sizes added in this batch (from job_add_sizes).")


@tool("print_setup", "Creates the job's Illustrator files, or with batch an add-on file for "
      "sizes added later (each starts from her closest existing artwork).",
      {"job_id": JOB_ID, "batch": BATCH}, ["job_id"])
def print_setup(a):
    return _adobe(f"/api/jobs/{a['job_id']}/illustrator/new-print-doc", a)


@tool("print_check", "Runs the print checks on her current Illustrator files without exporting "
      "or saving anything.", {"job_id": JOB_ID}, ["job_id"])
def print_check(a):
    return _adobe(f"/api/jobs/{a['job_id']}/illustrator/check-print", a)


@tool("print_export", "Checks and exports print (TIFF/PDF) with the right names. An open "
      "document with unsaved changes is saved first.", {"job_id": JOB_ID}, ["job_id"])
def print_export(a):
    return _adobe(f"/api/jobs/{a['job_id']}/illustrator/export-print", a)


@tool("digital_setup", "Creates the job's Photoshop file, or with batch adds artboards for sizes "
      "added later.", {"job_id": JOB_ID, "batch": BATCH}, ["job_id"])
def digital_setup(a):
    return _adobe(f"/api/jobs/{a['job_id']}/photoshop/new-digital-doc", a)


@tool("digital_export", "Exports every digital artboard from her PSD with the right names.",
      {"job_id": JOB_ID}, ["job_id"])
def digital_export(a):
    return _adobe(f"/api/jobs/{a['job_id']}/photoshop/export-digital", a)


@tool("video_get", "The job's video plan and settings: which Higgsfield masters to make, every "
      "video size with its mode (fit a master / motion from statics), fill (blur/black/color), "
      "how much fill shows, brand pieces, last render.", {"job_id": JOB_ID}, ["job_id"])
def video_get(a):
    return api("GET", f"/api/jobs/{a['job_id']}/video")


@tool("video_set_fill", "Fill behind the video where it doesn't cover a screen: blur, black or "
      "color, for the whole job or one size (format_id; fill 'job' = follow the job).",
      {"job_id": JOB_ID, "fill": _s("string", "blur / black / color / job"),
       "format_id": _s("string", ""), "brand_color": _s("string", "#rrggbb")},
      ["job_id", "fill"])
def video_set_fill(a):
    api("POST", f"/api/jobs/{a['job_id']}/video/fill", a)
    return {"fill": a["fill"]}


@tool("video_set_juice", "What must stay visible in a master (her 'juice box'): keys "
      "[{t: seconds, box: [x, y, w, h] as 0-1 fractions of the frame}]; per size with format_id.",
      {"job_id": JOB_ID, "master": _s("string", "Master id, e.g. m1."),
       "keys": _s("array", "Juice box keys."), "format_id": _s("string", "")},
      ["job_id", "master", "keys"])
def video_set_juice(a):
    api("POST", f"/api/jobs/{a['job_id']}/video/juice", a)
    return {"ok": True}


@tool("video_set_screen", "Per size: mode 'fit' (a Higgsfield master) or 'motion' (from her "
      "static), which master, repeat 1-4 (wrap-around columns).",
      {"job_id": JOB_ID, "format_id": _s("string", ""), "mode": _s("string", ""),
       "master": _s("string", ""), "repeat": _s("integer", "")}, ["job_id", "format_id"])
def video_set_screen(a):
    api("POST", f"/api/jobs/{a['job_id']}/video/screen", a)
    return {"ok": True}


@tool("video_set_source", "How this job's videos are made, for every size at once: 'motion' "
      "(her statics come alive) or 'fit' (one Higgsfield video fitted to every size).",
      {"job_id": JOB_ID, "source": _s("string", "motion / fit")}, ["job_id", "source"])
def video_set_source(a):
    api("POST", f"/api/jobs/{a['job_id']}/video/source", a)
    return {"source": a["source"]}


@tool("video_enable", "Also make a video for digital sizes of this job that only have a picture "
      "(video_get lists them as candidates). Adds an MP4 to their expected files; the picture "
      "still counts on its own.", {"job_id": JOB_ID, "format_ids": FORMAT_IDS},
      ["job_id", "format_ids"])
def video_enable(a):
    api("POST", f"/api/jobs/{a['job_id']}/video/enable", a)
    return {"ok": True}


MOTION_HELP = (
    "Motion from statics, with Figma's words. changes may hold: "
    "feel = easing for everything that moves: {type: gentle | quick | bouncy | slow} (Figma's "
    "springs), {type: spring, mass, stiffness, damping} (heavier mass = slower, swings further), "
    "or a curve {type: linear | ease-in | ease-out | ease-in-out | ease-in-back | ease-out-back | "
    "ease-in-out-back} or {type: bezier, points: [x1, y1, x2, y2]}; "
    "camera = {move: none | push-in | pull-out | pan-left | pan-right | pan-up | pan-down, "
    "amount: 0-30 %}; opening = dissolve | instant; ending = dissolve | hold | loop; "
    "second = how a size's 2nd picture takes over: {type: dissolve | slide-in | move-in | push | "
    "instant, direction: bottom | top | left | right (where it comes from), at: seconds or null "
    "(middle), duration: seconds}; length_s = 1-60; use_pieces = true/false. "
    "With format_id it's that size's own (reset: true = follow the job again).")


@tool("video_set_motion", MOTION_HELP,
      {"job_id": JOB_ID, "changes": _s("object", "Motion settings to change."),
       "format_id": _s("string", "One size only."), "reset": _s("boolean", ""),
       "recipes": _s("array", "Older form: push-in, crossfade, pieces-reveal, loop.",
                     items={"type": "string"}),
       "length_s": _s("number", "")}, ["job_id"])
def video_set_motion(a):
    data = api("POST", f"/api/jobs/{a['job_id']}/video/motion", a)
    return {"motion": data.get("motion")}


@tool("video_render", "Makes every video size (or format_ids) through her Concat, one by one, "
      "and exports each with its delivery name. Never overwrites an MP4 she made herself "
      "unless overwrite is true.",
      {"job_id": JOB_ID, "format_ids": FORMAT_IDS, "overwrite": _s("boolean", "")}, ["job_id"])
def video_render(a):
    return _task(f"/api/jobs/{a['job_id']}/video/render", a)


@tool("piece_update", "A brand piece (logo, line, promo text): anchor (top-left ... "
      "bottom-right, center), width_pct, margin_pct, enter {effect: dissolve | slide-in | move-in "
      "| scale-in | pop | instant, direction: bottom | top | left | right (where it comes from), "
      "at: seconds or null (auto, one after another), duration, easing: a feel like gentle / "
      "bouncy or null (the video's)}, exit null (stays) or {effect: dissolve | slide-out | "
      "move-out | scale-out, direction, at, duration, easing}; hidden (with format_id: leave it "
      "off that size).",
      {"job_id": JOB_ID, "piece_id": _s("string", ""), "changes": _s("object", ""),
       "format_id": _s("string", "")}, ["job_id", "piece_id", "changes"])
def piece_update(a):
    body = dict(a["changes"], **({"format_id": a["format_id"]} if a.get("format_id") else {}))
    return api("POST", f"/api/jobs/{a['job_id']}/pieces/{a['piece_id']}", body)


@tool("delivery_get", "What a delivery package for her manager would hold now: each file, "
      "ready or why not.", {"job_id": JOB_ID}, ["job_id"])
def delivery_get(a):
    return api("GET", f"/api/jobs/{a['job_id']}/delivery")


@tool("package_make", "Zips the files that passed their checks for her manager (a folder per "
      "group, README with notes). batch = only sizes added in that batch; include_warnings = "
      "send files with warnings too.",
      {"job_id": JOB_ID, "batch": BATCH, "include_warnings": _s("boolean", "")}, ["job_id"])
def package_make(a):
    return api("POST", f"/api/jobs/{a['job_id']}/delivery/package", dict(a, open=False))


# -- MCP over stdio ----------------------------------------------------------------------


def _reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method, msg_id = msg.get("method"), msg.get("id")
    if msg_id is None:
        return  # a notification
    if method == "initialize":
        _reply(msg_id, {"protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "studio-helper", "title": "Studio Helper",
                                       "version": __version__},
                        "instructions": INSTRUCTIONS})
    elif method == "ping":
        _reply(msg_id, {})
    elif method == "tools/list":
        _reply(msg_id, {"tools": [t["schema"] for t in TOOLS.values()]})
    elif method == "tools/call":
        params = msg.get("params") or {}
        entry = TOOLS.get(params.get("name"))
        if entry is None:
            _reply(msg_id, error={"code": -32602, "message": "Unknown tool."})
            return
        try:
            if not config.Config.load().assistants_enabled:
                raise ToolError("Assistant access is turned off in Studio Helper's Settings.")
            data = entry["fn"](params.get("arguments") or {})
            _reply(msg_id, {"content": [{"type": "text", "text": json.dumps(data, indent=1)}],
                            "structuredContent": data, "isError": False})
        except ToolError as exc:
            _reply(msg_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
    else:
        _reply(msg_id, error={"code": -32601, "message": f"Unknown method {method}."})


INSTRUCTIONS = (Path(__file__).parent / "assistant" / "SKILL.md").read_text(encoding="utf-8") \
    if (Path(__file__).parent / "assistant" / "SKILL.md").is_file() else ""


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _reply(None, error={"code": -32700, "message": "Parse error."})
            continue
        handle(msg)
    return 0
