"""Renders one screen's video through Concat (ROADMAP R6/R7).

A RenderPlan says what goes on the screen; render() turns it into Concat
edits in a project folder Studio Helper owns (03_working/video/<format>)
and exports it straight to the deliverable's file name. An existing
project is never overwritten: a rebuild renames it to .previous-<time>.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from studio_helper.validators.mp4 import audio_allowed

from . import fit as F
from .concat import ConcatError, ConcatSession

BLUR_AMOUNT = 0.6
DEFAULT_CRF = 20


@dataclass
class Layer:
    """One picture on the timeline: a video, a still or a brand piece."""
    file: str
    start: float = 0.0
    duration: float | None = None  # None: the media's own length
    scale: float = 1.0             # Concat units (1 = fits the frame)
    offset_x: float = 0.0
    offset_y: float = 0.0
    keys: list[dict] = field(default_factory=list)  # {"property", "at" (0-1), "value", "ease"?}
    fade_in: float = 0.0
    fade_out: float = 0.0
    muted: bool = False
    crop: dict | None = None       # fractions off each edge; Concat refits the rest


@dataclass
class RenderPlan:
    width: int
    height: int
    fps: int
    duration: float
    layers: list[Layer]            # bottom first
    background: dict               # Concat background: none / blur / color
    max_kb: float | None = None


def conform_fps(master_fps: float | None, required: float | None = None) -> int:
    """The screen's own rate, else the master's mapped to 25 or 30
    (Plamen, 2026-10-20): 24/25 -> 25, 30 -> 30, 50 -> 25, 60 -> 30."""
    if required:
        return round(required)
    if not master_fps:
        return 25
    base = master_fps / 2 if master_fps > 40 else master_fps
    return 25 if abs(base - 25) <= abs(base - 30) else 30


def background_for(fill: str, brand_color: str | None = None) -> dict:
    if fill == "blur":
        return {"kind": "blur", "amount": BLUR_AMOUNT}
    if fill == "color" and brand_color:
        return {"kind": "color", "color": brand_color}
    return {"kind": "none"}  # black


REPEAT_FRAME_PX = 4


def repeat_plan(fmt: dict, master: dict, master_path: str, n: int,
                brand_color: str | None = None, juice_keys: list[dict] | None = None
                ) -> RenderPlan:
    """The same fitted video in n columns with thin frame lines between
    them (the frame lines are the background: black or brand colour)."""
    sw, sh = master["w"], master["h"]
    dw, dh = fmt["size"]["w"], fmt["size"]["h"]
    juice = F.juice_box(juice_keys[0]["box"], sw, sh) if juice_keys else None
    duration = master["duration_s"]
    if fmt.get("max_duration_s"):
        duration = min(duration, fmt["max_duration_s"])
    layers = [Layer(file=master_path, duration=duration, scale=pl.concat_scale,
                    offset_x=pl.offset_x, offset_y=pl.offset_y, crop=pl.crop,
                    muted=not audio_allowed(fmt) or i > 0)
              for i, pl in enumerate(F.repeat_panels(sw, sh, dw, dh, n, REPEAT_FRAME_PX, juice))]
    return RenderPlan(width=dw, height=dh, fps=conform_fps(master.get("fps"), fmt.get("fps")),
                      duration=duration, layers=layers,
                      background=background_for("color" if brand_color else "black",
                                                brand_color),
                      max_kb=fmt.get("max_kb"))


def fitter_plan(fmt: dict, master: dict, master_path: str, fill: str,
                brand_color: str | None = None, juice_keys: list[dict] | None = None,
                pieces: list[Layer] | None = None) -> tuple[RenderPlan, list[tuple[float, F.Fit]]]:
    """The plan for one screen from one master: fitted around her juice
    box, trimmed to the screen's limit, silent where screens are."""
    sw, sh = master["w"], master["h"]
    dw, dh = fmt["size"]["w"], fmt["size"]["h"]
    band = fmt.get("ui_safe_px") or {}
    keys = [(k["t"], F.juice_box(k["box"], sw, sh)) for k in (juice_keys or [])]
    fits = F.fit_keyed(sw, sh, dw, dh, keys, band.get("top", 0), band.get("bottom", 0))
    duration = master["duration_s"]
    if fmt.get("max_duration_s"):
        duration = min(duration, fmt["max_duration_s"])
    first = fits[0][1]
    layer = Layer(file=master_path, duration=duration, scale=first.concat_scale,
                  offset_x=first.offset_x, offset_y=first.offset_y,
                  muted=not audio_allowed(fmt),
                  # Concat's clip fade: the sound fades with the picture's black fade
                  fade_out=0.3 if duration < master["duration_s"] else 0.0)
    if len(fits) > 1:
        for t, f in fits:
            at = min(max(t / duration, 0.0), 1.0)
            layer.keys.append({"property": "offsetX", "at": at, "value": f.offset_x})
            layer.keys.append({"property": "offsetY", "at": at, "value": f.offset_y})
    plan = RenderPlan(
        width=dw, height=dh, fps=conform_fps(master.get("fps"), fmt.get("fps")),
        duration=duration, layers=[layer] + list(pieces or []),
        background=background_for(fill, brand_color), max_kb=fmt.get("max_kb"),
    )
    return plan, fits


BLACK_DIR = "03_working/video"


def black_still(root: Path, w: int, h: int) -> Path:
    """A black picture at the screen's own shape, for fades to and from
    black (Concat's clip fadeIn/fadeOut don't darken the picture; checked
    on Concat 0.2.8)."""
    path = root / BLACK_DIR / f"_black_{w}x{h}.png"
    if not path.is_file():
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h)).save(path)
    return path


def fade_layers(root: Path, plan: RenderPlan, fade_in: float, fade_out: float) -> list[Layer]:
    """Black on top: dissolving away at the start, in at the end."""
    from . import motion as M

    out = []
    black = str(black_still(root, plan.width, plan.height))
    if fade_in > 0:
        layer = Layer(file=black, start=0.0, duration=fade_in)
        layer.keys = M.all_keys({}, [M.Seg("opacity", 0.0, fade_in, 1.0, 0.0,
                                           {"type": "ease-in-out"})], fade_in)
        out.append(layer)
    if fade_out > 0:
        start = max(plan.duration - fade_out, 0.0)
        layer = Layer(file=black, start=start, duration=plan.duration - start)
        layer.keys = M.all_keys({}, [M.Seg("opacity", 0.0, plan.duration - start, 0.0, 1.0,
                                           {"type": "ease-in-out"})], plan.duration - start)
        out.append(layer)
    return out


def _fresh_project_dir(project_dir: Path) -> None:
    """Never overwrite her (or our) earlier project: move it aside."""
    if project_dir.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        project_dir.rename(project_dir.with_name(f"{project_dir.name}.previous-{stamp}"))


def build(c: ConcatSession, plan: RenderPlan, project_dir: Path) -> str:
    """Creates the Concat project for a plan. Returns its path."""
    _fresh_project_dir(project_dir)
    project_dir.parent.mkdir(parents=True, exist_ok=True)
    c.call("project_create", location=str(project_dir.parent), name=project_dir.name,
           video={"width": plan.width, "height": plan.height, "rateNum": plan.fps, "rateDen": 1})
    path = str(project_dir)
    timeline = c.call("timeline_read", path=path)["timeline"]
    tracks = [t["id"] for t in timeline["tracks"]]  # top to bottom
    while len(tracks) < len(plan.layers):
        c.call("track_add", path=path, bottom=False)
        tracks = [t["id"] for t in c.call("timeline_read", path=path)["timeline"]["tracks"]]
    # Lanes draw in list order: the last one is on top (checked on Concat
    # 0.2.8 -- its docs say "top to bottom", the renderer does the reverse).
    lanes = tracks  # bottom first, like plan.layers
    media_ids: dict[str, str] = {}
    for i, layer in enumerate(plan.layers):
        media = media_ids.get(layer.file)
        if media is None:
            # importing a file already in the bin returns no new id
            media = c.call("media_import", path=path, file=layer.file)["createdId"]
            media_ids[layer.file] = media
        clip = c.call("clip_add", path=path, mediaId=media, trackId=lanes[i],
                      start=layer.start)["createdId"]
        _shape_clip(c, path, clip, layer, plan)
    c.call("timeline_background", path=path, timelineId=timeline["id"],
           background=plan.background)
    c.call("project_save", path=path)
    return path


def _clip(c, path, clip_id) -> dict:
    clips = c.call("timeline_read", path=path)["timeline"]["clips"]
    return next(cl for cl in clips if cl["id"] == clip_id)


def _shape_clip(c, path, clip_id, layer: Layer, plan: RenderPlan) -> None:
    want = layer.duration if layer.duration is not None else plan.duration - layer.start
    have = _clip(c, path, clip_id)["duration"]
    if abs(have - want) > 1e-3:
        c.call("clip_trim", path=path, clipId=clip_id, edge="end", delta=want - have)
    c.call("clip_transform", path=path, clipId=clip_id, scale=layer.scale,
           offsetX=layer.offset_x, offsetY=layer.offset_y)
    patch = {}
    if layer.crop:
        patch["crop"] = layer.crop
    if layer.muted:
        patch["muted"] = True
    if layer.fade_in:
        patch["fadeIn"] = layer.fade_in
    if layer.fade_out:
        patch["fadeOut"] = layer.fade_out
    if patch:
        c.call("clip_update", path=path, clipId=clip_id, patch=patch)
    for k in layer.keys:
        c.call("keyframe_set", path=path, clipId=clip_id, property=k["property"], at=k["at"],
               value=k["value"], ease=k.get("ease"))


def export(c: ConcatSession, path: str, plan: RenderPlan, output: Path,
           on_progress: Callable[[float], None] | None = None, crf: int = DEFAULT_CRF) -> Path:
    """Exports to `output`; re-exports once at a lower quality if the
    screen's file-size limit is passed."""
    _export_once(c, path, plan, output, on_progress, crf)
    if plan.max_kb and output.stat().st_size / 1024 > plan.max_kb:
        ratio = output.stat().st_size / 1024 / (plan.max_kb * 0.9)
        # x264: about +6 crf halves the size
        bump = max(3, round(6 * _log2(ratio)) + 1)
        _export_once(c, path, plan, output, on_progress, min(crf + bump, 40))
        if output.stat().st_size / 1024 > plan.max_kb:
            raise ConcatError(f"The video is still over this screen's "
                              f"{plan.max_kb / 1024:.0f} MB limit. Shorten it, or simplify it.")
    return output


def _log2(x: float) -> float:
    import math
    return math.log2(max(x, 1.0))


def _export_once(c, path, plan, output: Path, on_progress, crf: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    job = c.call("export_start", path=path, output=str(output), crf=crf,
                 width=plan.width, height=plan.height, rateNum=plan.fps, rateDen=1)["job"]
    while True:
        status = c.call("export_wait", job=job, timeoutSeconds=60, timeout=90,
                        on_progress=(lambda p: on_progress(p.get("progress", 0) /
                                                           max(p.get("total") or 1, 1)))
                        if on_progress else None)
        state = status.get("state")
        if state == "done":
            return
        if state in ("failed", "cancelled"):
            err = status.get("error") or {}
            raise ConcatError(err.get("message") or f"The export {state}.")
