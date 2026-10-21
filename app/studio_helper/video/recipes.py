"""Motion from statics and brand pieces (ROADMAP R7).

Motion only moves what she designed: her static for each size (or a
cleaner version of it she picks, without the logo she animates) and her
brand pieces (logo, the line under it, promo text...). It never
generates text or layout.

A motion video, from job["video"]["motion"] (per size in
screens[<id>]["motion"]; the words and curves are Figma's, motion.py):

  feel      the easing for everything that moves: gentle (default),
            quick, bouncy, slow, a spring of her own (mass, stiffness,
            damping) or a curve (ease out, ease in and out, ...)
  camera    a slow move on the picture: push in, pull out, pan; amount %
  opening   instant, or dissolve from black
  second    with a 2nd picture for the size: how it takes over
            (dissolve, slide in, move in, push; from a direction; when)
  ending    hold, dissolve to black, or loop (back into the first frame)
  pieces    her brand pieces come in one after another

Older jobs stored a list of "recipes" (push-in, crossfade,
pieces-reveal, loop); motion_settings() reads those as the same choices.
"""

from __future__ import annotations

import copy
from pathlib import Path

from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND

from . import motion as M
from .render import Layer, RenderPlan, background_for, conform_fps, fade_layers

DEFAULT_LENGTH_S = 8.0
OPEN_S = 0.5     # dissolve from black
END_S = 0.6      # dissolve to black, or back into the first frame (loop)

ANCHORS = ("top-left", "top-center", "top-right", "middle-left", "center", "middle-right",
           "bottom-left", "bottom-center", "bottom-right")
PIECE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
PICTURE_EXTS = {".png", ".jpg", ".jpeg"}
STAGGER_S = 0.35
ENTER_S = 0.6     # a curve's length; a spring's comes from the spring
PIECE_GAP = 0.015  # fraction of the frame height between stacked pieces

OPENINGS = ("dissolve", "instant")
ENDINGS = ("dissolve", "hold", "loop")

MOTION_DEFAULTS = {
    "feel": dict(M.DEFAULT_FEEL),
    "camera": {"move": "push-in", "amount": 6},
    "opening": "dissolve",
    "ending": "dissolve",
    "second": {"type": "dissolve", "direction": "right", "at": None, "duration": 0.8},
    "length_s": DEFAULT_LENGTH_S,
    "use_pieces": True,
}
MOTION_KEYS = tuple(MOTION_DEFAULTS)

# older brand-piece effects -> the Figma names
_OLD_EFFECTS = {"fade": ("dissolve", "bottom"), "fade-up": ("slide-in", "bottom")}


def _from_recipes(recipes: list[str]) -> dict:
    """The motion settings an older job's recipe list meant."""
    return {"camera": {"move": "push-in" if "push-in" in recipes else "none", "amount": 6},
            "ending": "loop" if "loop" in recipes else "dissolve",
            "use_pieces": "pieces-reveal" in recipes}


def _merge(base: dict, over: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k not in MOTION_KEYS:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "feel":
            out[k] = {**out[k], **v}
        else:
            out[k] = copy.deepcopy(v)
    return out


def motion_settings(job: dict, fmt: dict | None = None) -> dict:
    """The job's motion choices, with one size's own on top."""
    v = job.get("video", {})
    m = v.get("motion") or {}
    out = copy.deepcopy(MOTION_DEFAULTS)
    if "recipes" in m:
        out = _merge(out, _from_recipes(m["recipes"]))
    out = _merge(out, m)
    if fmt is not None:
        own = v.get("screens", {}).get(fmt["id"], {})
        if "recipes" in own:
            out = _merge(out, _from_recipes(own["recipes"]))
        out = _merge(out, own.get("motion"))
    if fmt is not None and fmt.get("max_duration_s"):
        out["length_s"] = min(float(out["length_s"]), float(fmt["max_duration_s"]))
    out["feel"] = M.clean_easing(out["feel"])
    return out


def clean_motion(changes: dict) -> dict:
    """Checks motion settings from the UI or an assistant."""
    out = {}
    for k, val in changes.items():
        if k not in MOTION_KEYS:
            raise M.MotionError(f"Unknown motion setting '{k}'.")
        if k == "feel":
            out[k] = M.clean_easing(val)
        elif k == "camera":
            move = val.get("move", "none")
            if move not in M.CAMERA_MOVES:
                raise M.MotionError(f"Camera move must be one of {', '.join(M.CAMERA_MOVES)}.")
            amount = float(val.get("amount", 6))
            if not 0 <= amount <= 30:
                raise M.MotionError("Camera amount must be 0 to 30%.")
            out[k] = {"move": move, "amount": amount}
            if val.get("easing") is not None:
                out[k]["easing"] = M.clean_easing(val["easing"])
        elif k == "opening":
            if val not in OPENINGS:
                raise M.MotionError("Opening must be dissolve or instant.")
            out[k] = val
        elif k == "ending":
            if val not in ENDINGS:
                raise M.MotionError("Ending must be dissolve, hold or loop.")
            out[k] = val
        elif k == "second":
            out[k] = _clean_transition(val)
        elif k == "length_s":
            if not 1 <= float(val) <= 60:
                raise M.MotionError("Length must be between 1 and 60 seconds.")
            out[k] = float(val)
        elif k == "use_pieces":
            out[k] = bool(val)
    return out


def _clean_transition(val: dict) -> dict:
    kind = val.get("type", "dissolve")
    if kind not in M.TRANSITIONS:
        raise M.MotionError(f"Transition must be one of {', '.join(M.TRANSITIONS)}.")
    direction = val.get("direction", "right")
    if direction not in M.DIRECTIONS:
        raise M.MotionError("Direction must be bottom, top, left or right.")
    out = {"type": kind, "direction": direction,
           "at": None if val.get("at") in (None, "") else float(val["at"]),
           "duration": min(max(float(val.get("duration", 0.8)), 0.1), 5.0)}
    if val.get("easing") is not None:
        out["easing"] = M.clean_easing(val["easing"])
    return out


def motion_length(job: dict, fmt: dict) -> float:
    return float(motion_settings(job, fmt)["length_s"])


def static_for(job: dict, fmt: dict, root: Path) -> Path | None:
    """The picture motion starts from: the one she picked for this size
    (e.g. her design without the logo she animates), else her exported
    static (PNG first; the Paradise column takes no JPG)."""
    own = job.get("video", {}).get("motion", {}).get("a_files", {}).get(fmt["id"])
    if own and (root / own).is_file():
        return root / own
    folder = root / "04_export" / EXPORT_SUBDIR_BY_KIND[fmt["kind"]]
    for kind in ("png", "jpg"):
        for d in job["deliverables"]:
            if d["format_id"] == fmt["id"] and d["type"] == kind:
                p = folder / f"{d['expected_stem']}.{kind}"
                if p.is_file():
                    return p
    return None


def second_for(job: dict, fmt: dict, root: Path) -> Path | None:
    rel = job.get("video", {}).get("motion", {}).get("b_files", {}).get(fmt["id"])
    return root / rel if rel and (root / rel).is_file() else None


# -- brand pieces --------------------------------------------------------------


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.size


def _anchor_xy(anchor: str, dw, dh, w, h, margin, top_band, bottom_band):
    vert, _, horiz = anchor.partition("-") if "-" in anchor else ("middle", "", "center")
    if anchor == "center":
        vert, horiz = "middle", "center"
    x = {"left": margin + w / 2, "center": dw / 2, "right": dw - margin - w / 2}[horiz]
    y = {"top": top_band + margin + h / 2, "middle": dh / 2,
         "bottom": dh - bottom_band - margin - h / 2}[vert]
    return x, y


def piece_motion(piece: dict, feel: dict) -> tuple[dict, dict | None]:
    """A piece's entrance and exit with every default filled in."""
    enter = dict(piece.get("enter") or {})
    effect = enter.get("effect", "slide-in")
    if effect in _OLD_EFFECTS:
        effect, direction = _OLD_EFFECTS[effect]
        enter.setdefault("direction", direction)
    if effect not in M.ENTER_EFFECTS:
        effect = "slide-in"
    enter["effect"] = effect
    enter.setdefault("direction", "bottom")
    enter["easing"] = M.clean_easing(enter.get("easing") or feel)
    enter["length"] = M.duration(enter["easing"], float(enter.get("duration") or ENTER_S))
    leave = piece.get("exit")
    if leave and leave.get("effect") in M.EXIT_EFFECTS:
        leave = dict(leave)
        leave.setdefault("direction", "bottom")
        leave["easing"] = M.clean_easing(leave.get("easing") or feel)
        leave["length"] = M.duration(leave["easing"], float(leave.get("duration") or ENTER_S))
    else:
        leave = None
    return enter, leave


def piece_layers(job: dict, fmt: dict, root: Path, end_s: float | None = None,
                 mode: str = "end-card") -> list[Layer]:
    """Her brand pieces as layers for one screen: placed at their anchor
    (inside the platform's UI bands), stacked in list order, coming in
    one after another. mode "end-card" (over a Higgsfield video) brings
    them in over the last 2 s; "motion" (over her static) right after
    the opening."""
    pieces = job.get("pieces") or []
    if not pieces:
        return []
    dw, dh = fmt["size"]["w"], fmt["size"]["h"]
    band = fmt.get("ui_safe_px") or {}
    top_band, bottom_band = band.get("top", 0), band.get("bottom", 0)
    over = job.get("video", {}).get("screens", {}).get(fmt["id"], {}).get("pieces", {})
    settings = motion_settings(job, fmt)
    feel = settings["feel"]
    length = end_s if end_s is not None else settings["length_s"]

    placed = []
    for i, p in enumerate(pieces):
        path = root / p["file"]
        if not path.is_file() or path.suffix.lower() not in PIECE_EXTS:
            continue
        o = dict(p, **over.get(p["id"], {}))
        if o.get("hidden"):
            continue
        pw, ph = _image_size(path)
        w = dw * float(o.get("width_pct", 30)) / 100
        h = w * ph / pw
        if h > dh * 0.3:  # keep a tall piece from eating a strip
            h = dh * 0.3
            w = h * pw / ph
        placed.append((i, o, path, pw, ph, w, h))

    # stack pieces that share an anchor, in list order
    layers = []
    by_anchor: dict[str, list] = {}
    for item in placed:
        by_anchor.setdefault(item[1].get("anchor", "bottom-center"), []).append(item)
    order = {item[0]: n for n, item in enumerate(placed)}
    for anchor, items in by_anchor.items():
        gap = PIECE_GAP * dh
        total_h = sum(it[6] for it in items) + gap * (len(items) - 1)
        margin = min(dw, dh) * float(items[0][1].get("margin_pct", 5)) / 100
        _gx, gy = _anchor_xy(anchor, dw, dh, max(it[5] for it in items), total_h, margin,
                             top_band, bottom_band)
        y = gy - total_h / 2
        for i, o, path, pw, ph, w, h in items:
            cx = _anchor_xy(anchor, dw, dh, w, h, margin, top_band, bottom_band)[0]
            cy = y + h / 2
            y += h + gap
            fit_scale = min(dw / pw, dh / ph)
            enter, leave = piece_motion(o, feel)
            start = _enter_at(enter, order[i], length, mode)
            clip_len = max(length - start, 0.1)
            scale = (w / pw) / fit_scale
            offset = ((cx - dw / 2) / dw, (cy - dh / 2) / dh)
            layer = Layer(file=str(path), start=start, duration=clip_len, scale=scale,
                          offset_x=offset[0], offset_y=offset[1])
            size_frac = (w / dw, h / dh)
            segs = M.enter(enter["effect"], enter["direction"], enter["easing"], 0.0,
                           min(enter["length"], clip_len), size_frac, offset)
            if leave:
                at = leave.get("at")
                t = (float(at) - start) if at is not None else clip_len - leave["length"]
                t = min(max(t, enter["length"]), max(clip_len - 0.05, 0.0))
                segs += M.leave(leave["effect"], leave["direction"], leave["easing"], t,
                                min(leave["length"], clip_len - t), size_frac, offset)
            layer.keys = M.all_keys({"scale": scale, "offsetX": offset[0], "offsetY": offset[1],
                                     "opacity": 1.0}, segs, clip_len)
            layers.append((i, layer))
    return [layer for _i, layer in sorted(layers, key=lambda t: t[0])]


def _enter_at(enter: dict, index: int, length: float, mode: str) -> float:
    if enter.get("at") is not None:
        return min(max(float(enter["at"]), 0.0), max(length - 0.2, 0.0))
    if mode == "motion":
        # right after the opening, one after another
        return min(OPEN_S + 0.4 + index * STAGGER_S, max(length - 1.0, 0.0))
    # an end card: one after another, the last ~1 s before the end
    first = max(length - 2.0, 0.0)
    return min(first + index * STAGGER_S, max(length - 0.6, 0.0))


def add_pieces(plan: RenderPlan, pieces: list[Layer]) -> None:
    """Pieces over a fitted master (an end card)."""
    plan.layers.extend(pieces)


# -- motion from statics ----------------------------------------------------------


def motion_plan(job: dict, fmt: dict, root: Path, pieces: list[Layer] | None = None) -> RenderPlan:
    from .service import VideoError

    a = static_for(job, fmt, root)
    if a is None:
        raise VideoError("Export the static for this size first (or pick a picture for it): "
                         "motion starts from it.")
    s = motion_settings(job, fmt)
    length = float(s["length_s"])
    feel = s["feel"]
    cam = s["camera"]
    cam_ease = M.clean_easing(cam.get("easing") or "ease-in-out")
    b = second_for(job, fmt, root)

    a_segs: list = []
    b_layer = None
    if b is not None:
        tr = s["second"]
        t_ease = M.clean_easing(tr.get("easing") or feel)
        t_len = M.duration(t_ease, tr["duration"])
        at = tr["at"] if tr["at"] is not None else length / 2 - t_len / 2
        at = min(max(float(at), 0.2), max(length - t_len - 0.2, 0.2))
        a_move, b_move = M.transition(tr["type"], tr["direction"], t_ease, at, t_len)
        a_segs += a_move
        b_len = length - at
        b_scale, b_cam = M.camera(cam["move"], cam["amount"], 0.0, b_len, cam_ease)
        b_layer = Layer(file=str(b), start=at, duration=b_len, scale=b_scale)
        b_layer.keys = M.all_keys({"scale": b_scale}, b_move + b_cam, b_len)
    a_scale, a_cam = M.camera(cam["move"], cam["amount"], 0.0, length, cam_ease)
    a_segs += a_cam
    base = Layer(file=str(a), duration=length, scale=a_scale)
    base.keys = M.all_keys({"scale": a_scale}, a_segs, length)
    layers = [base]
    if b_layer is not None:
        layers.append(b_layer)
    if s["use_pieces"]:
        layers.extend(pieces if pieces is not None
                      else piece_layers(job, fmt, root, length, "motion"))
    if s["ending"] == "loop":
        # the end dissolves into exactly the first frame, so a looping screen doesn't jump
        start = max(length - END_S, 0.0)
        first = {"scale": a_scale, "offsetX": M.value_at("offsetX", 0.0, a_cam, 0.0),
                 "offsetY": M.value_at("offsetY", 0.0, a_cam, 0.0)}
        tail = Layer(file=str(a), start=start, duration=length - start, scale=first["scale"],
                     offset_x=first["offsetX"], offset_y=first["offsetY"])
        tail.keys = M.all_keys({"opacity": 1.0},
                               [M.Seg("opacity", 0.0, length - start, 0.0, 1.0,
                                      {"type": "ease-in-out"})], length - start)
        layers.append(tail)
    plan = RenderPlan(width=fmt["size"]["w"], height=fmt["size"]["h"],
                      fps=conform_fps(None, fmt.get("fps")) if fmt.get("fps") else 25,
                      duration=length, layers=layers, background=background_for("black"),
                      max_kb=fmt.get("max_kb"))
    loop = s["ending"] == "loop"
    plan.layers += fade_layers(root, plan, OPEN_S if s["opening"] == "dissolve" and not loop
                               else 0.0, END_S if s["ending"] == "dissolve" else 0.0)
    return plan
