"""Motion from statics and brand pieces (ROADMAP R7).

Recipes only move what she designed: her static exports and her brand
pieces (logo, the line under it, promo text...). They never generate
text or layout.

Recipes (combinable):
  push-in        the static zooms 100 -> 106% with a fade in and out
  crossfade      static A, then a 1 s crossfade to static B
  pieces-reveal  her brand pieces enter one after another near the end
  loop           the end fades back into the first frame (looping screens)
"""

from __future__ import annotations

from pathlib import Path

from studio_helper.core.scaffold import EXPORT_SUBDIR_BY_KIND

from .render import Layer, RenderPlan, background_for, conform_fps

RECIPES = ("push-in", "crossfade", "pieces-reveal", "loop")
DEFAULT_RECIPES = ["push-in", "pieces-reveal"]
DEFAULT_LENGTH_S = 8.0
PUSH_ZOOM = 1.06
EASE_OUT = [0.25, 0.1, 0.25, 1.0]

ANCHORS = ("top-left", "top-center", "top-right", "middle-left", "center", "middle-right",
           "bottom-left", "bottom-center", "bottom-right")
EFFECTS = ("fade", "fade-up", "scale-in", "pop")
PIECE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
STAGGER_S = 0.4
ENTER_S = 0.6
PIECE_GAP = 0.015  # fraction of the frame height between stacked pieces


def job_recipes(job: dict, fmt: dict) -> list[str]:
    v = job.get("video", {})
    own = v.get("screens", {}).get(fmt["id"], {}).get("recipes")
    chosen = own or v.get("motion", {}).get("recipes") or DEFAULT_RECIPES
    return [r for r in chosen if r in RECIPES]


def motion_length(job: dict, fmt: dict) -> float:
    length = float(job.get("video", {}).get("motion", {}).get("length_s") or DEFAULT_LENGTH_S)
    if fmt.get("max_duration_s"):
        length = min(length, float(fmt["max_duration_s"]))
    return length


def static_for(job: dict, fmt: dict, root: Path) -> Path | None:
    """Her exported static for this size (PNG preferred, the Paradise
    column takes no JPG)."""
    folder = root / "04_export" / EXPORT_SUBDIR_BY_KIND[fmt["kind"]]
    for kind in ("png", "jpg"):
        for d in job["deliverables"]:
            if d["format_id"] == fmt["id"] and d["type"] == kind:
                p = folder / f"{d['expected_stem']}.{kind}"
                if p.is_file():
                    return p
    return None


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


def piece_layers(job: dict, fmt: dict, root: Path, end_s: float | None = None) -> list[Layer]:
    """Her brand pieces as layers for one screen: placed at their anchor
    (inside the platform's UI bands), stacked in list order, entering one
    after another and staying to the end."""
    pieces = job.get("pieces") or []
    if not pieces:
        return []
    dw, dh = fmt["size"]["w"], fmt["size"]["h"]
    band = fmt.get("ui_safe_px") or {}
    top_band, bottom_band = band.get("top", 0), band.get("bottom", 0)
    over = job.get("video", {}).get("screens", {}).get(fmt["id"], {}).get("pieces", {})
    length = end_s if end_s is not None else motion_length(job, fmt)

    placed = []
    for i, p in enumerate(pieces):
        path = root / p["file"]
        if not path.is_file() or path.suffix.lower() not in PIECE_EXTS:
            continue
        o = dict(p, **over.get(p["id"], {}))
        pw, ph = _image_size(path)
        w = dw * float(o.get("width_pct", 30)) / 100
        h = w * ph / pw
        if h > dh * 0.3:  # keep a tall piece from eating a strip
            h = dh * 0.3
            w = h * pw / ph
        placed.append((i, o, path, pw, ph, w, h))

    # stack pieces that share an anchor, in list order
    layers = []
    margin_of = {}
    by_anchor: dict[str, list] = {}
    for item in placed:
        by_anchor.setdefault(item[1].get("anchor", "bottom-center"), []).append(item)
    for anchor, items in by_anchor.items():
        gap = PIECE_GAP * dh
        total_h = sum(it[6] for it in items) + gap * (len(items) - 1)
        margin = min(dw, dh) * float(items[0][1].get("margin_pct", 5)) / 100
        margin_of[anchor] = margin
        gx, gy = _anchor_xy(anchor, dw, dh, max(it[5] for it in items), total_h, margin,
                            top_band, bottom_band)
        y = gy - total_h / 2
        for i, o, path, pw, ph, w, h in items:
            cx = _anchor_xy(anchor, dw, dh, w, h, margin, top_band, bottom_band)[0]
            cy = y + h / 2
            y += h + gap
            fit_scale = min(dw / pw, dh / ph)
            start = _enter_at(o, i, length)
            layer = Layer(file=str(path), start=start, duration=max(length - start, 0.1),
                          scale=(w / pw) / fit_scale, offset_x=(cx - dw / 2) / dw,
                          offset_y=(cy - dh / 2) / dh)
            _entrance(layer, o, length - start)
            layers.append((i, layer))
    return [layer for _i, layer in sorted(layers, key=lambda t: t[0])]


def _enter_at(piece: dict, index: int, length: float) -> float:
    enter = piece.get("enter") or {}
    if enter.get("at") is not None:
        return min(max(float(enter["at"]), 0.0), max(length - 0.2, 0.0))
    # by default the pieces arrive one after another, ending ~1 s before the end
    first = max(length - 2.0, 0.0)
    return min(first + index * STAGGER_S, max(length - 0.6, 0.0))


def _entrance(layer: Layer, piece: dict, clip_len: float) -> None:
    effect = (piece.get("enter") or {}).get("effect", "fade-up")
    dur = float((piece.get("enter") or {}).get("duration", ENTER_S))
    end = min(dur / max(clip_len, 0.01), 1.0)
    layer.keys.append({"property": "opacity", "at": 0.0, "value": 0.0})
    layer.keys.append({"property": "opacity", "at": end, "value": 1.0, "ease": EASE_OUT})
    if effect == "fade-up":
        layer.keys.append({"property": "offsetY", "at": 0.0, "value": layer.offset_y + 0.03})
        layer.keys.append({"property": "offsetY", "at": end, "value": layer.offset_y,
                           "ease": EASE_OUT})
    elif effect in ("scale-in", "pop"):
        start = 0.9 if effect == "scale-in" else 1.05
        layer.keys.append({"property": "scale", "at": 0.0, "value": layer.scale * start})
        layer.keys.append({"property": "scale", "at": end, "value": layer.scale,
                           "ease": EASE_OUT})


def add_pieces(plan: RenderPlan, pieces: list[Layer]) -> None:
    """Pieces over a fitted master (an end card): re-timed to its length."""
    plan.layers.extend(pieces)


# -- motion from statics ----------------------------------------------------------


def motion_plan(job: dict, fmt: dict, root: Path, pieces: list[Layer] | None = None) -> RenderPlan:
    from .service import VideoError

    a = static_for(job, fmt, root)
    if a is None:
        raise VideoError("Export the static for this size first: motion starts from it.")
    chosen = job_recipes(job, fmt)
    length = motion_length(job, fmt)
    layers: list[Layer] = []
    base = Layer(file=str(a), duration=length, fade_in=0.5 if "loop" not in chosen else 0.0)
    if "push-in" in chosen:
        base.keys += [{"property": "scale", "at": 0.0, "value": 1.0},
                      {"property": "scale", "at": 1.0, "value": PUSH_ZOOM}]
        if "loop" not in chosen:
            base.fade_out = 0.5
    layers.append(base)
    b_rel = job.get("video", {}).get("motion", {}).get("b_files", {}).get(fmt["id"])
    if "crossfade" in chosen and b_rel and (root / b_rel).is_file():
        start = length / 2 - 0.5
        b = Layer(file=str(root / b_rel), start=start, duration=length - start)
        b.keys = [{"property": "opacity", "at": 0.0, "value": 0.0},
                  {"property": "opacity", "at": 1.0 / max(length - start, 1), "value": 1.0}]
        layers.append(b)
    if "pieces-reveal" in chosen:
        layers.extend(pieces if pieces is not None else piece_layers(job, fmt, root, length))
    if "loop" in chosen:
        # the end fades into exactly the first frame, so a looping screen doesn't jump
        tail = Layer(file=str(a), start=max(length - 0.5, 0.0), duration=0.5)
        tail.keys = [{"property": "opacity", "at": 0.0, "value": 0.0},
                     {"property": "opacity", "at": 1.0, "value": 1.0}]
        layers.append(tail)
    return RenderPlan(width=fmt["size"]["w"], height=fmt["size"]["h"],
                      fps=conform_fps(None, fmt.get("fps")) if fmt.get("fps") else 25,
                      duration=length, layers=layers, background=background_for("black"),
                      max_kb=fmt.get("max_kb"))
